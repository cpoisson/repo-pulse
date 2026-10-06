# repo-pulse guide

The details behind the [README](../README.md): commands, indicators, how the issue classifier is chosen, scheduled runs,
grounding, cost and caveats.

- [Commands](#commands)
- [Installing the skill](#installing-the-skill)
- [Configuration](#configuration)
- [The deck](#the-deck)
- [Indicators](#indicators)
- [Issue triage: chosen by measurement](#issue-triage-chosen-by-measurement)
- [Narrative and grounding](#narrative-and-grounding)
- [Scheduled editions](#scheduled-editions)
- [Example decks](#example-decks)
- [Token budget](#token-budget)
- [Caveats](#caveats)
- [Development](#development)

## Commands

```bash
uv sync --extra local-models                            # core + local issue classifiers
uv run repo-pulse init owner/name                       # clone + configs/name.yaml
C=configs/name.yaml
uv run repo-pulse -c $C collect                         # GitHub, git, PyPI (cached)
uv run repo-pulse -c $C issues --chars 160              # issue list, to propose the theme taxonomy
uv run repo-pulse -c $C gold --prelabels labels.txt     # gold set: "<number> <type> <theme>" per line, "-" excludes
uv run repo-pulse -c $C bakeoff --models rules,ModernBERT-base_issue-type,bge-base-en-v1.5+LR
uv run repo-pulse -c $C classify
uv run repo-pulse -c $C analyze
uv run repo-pulse -c $C digest                          # ~2k-token summary the narrative is written from
uv run repo-pulse -c $C narrate                         # narrative file, optional API call, or rules
uv run repo-pulse -c $C build                           # out/<name>-pulse-<date>.html
uv run repo-pulse -c $C all                             # collect → classify → analyze → narrate → build
```

Every command takes `--as-of YYYY-MM-DD` (default: today). Auth uses the `gh` CLI. Raw data is cached in
`data/raw/<repo>/<date>/`, so reruns are free. Each run also appends exact counters (stars, forks, open issues) to
`data/history/<repo>.jsonl`, which makes later trends precise.

The judgment steps (theme taxonomy, gold labels, narrative) are described in
[`skills/repo-pulse/SKILL.md`](../skills/repo-pulse/SKILL.md), which any coding agent can follow.

## Installing the skill

The skill is a plain [SKILL.md](../skills/repo-pulse/SKILL.md) folder (with `references/` and `scripts/`), so it is not
tied to one agent.

- **Any agent, with the [skills](https://skills.sh) installer:** `npx skills add cpoisson/repo-pulse`. Add `-g` to install
  for your user instead of the current project, `-a <agent>` to pick agents (e.g. `-a codex -a cursor`), `-y` to skip
  prompts. It installs to each agent's skills folder (for example `.agents/skills/` for Codex and Cursor).
- **By hand:** copy or link `skills/repo-pulse/` into your agent's skills folder.
- **No skill support:** tell the agent to clone the repo and follow `skills/repo-pulse/SKILL.md`.

An installed skill does not need a checkout: its setup step uses the current directory if it is a repo-pulse checkout,
else `$REPO_PULSE_HOME`, else `~/.local/share/repo-pulse`, cloning the tool there on first use and pulling updates
later. Configs, data and decks live in that checkout, so later editions find the earlier ones.

## Configuration

Repo-specific details live in `configs/<name>.yaml`: module map, theme taxonomy, critical dependencies, thresholds,
classifier policy. `repo-pulse init owner/name` writes a starter one and `configs/_template.yaml` documents every field.
Configs and their `data/` artifacts are local (gitignored), so the repo stays generic. Clones go to
`$REPO_PULSE_CLONES` (default `~/.cache/repo-pulse/clones`), shallow to the analysis window.

## The deck

One self-contained HTML file: fixed 16:9 slides, keyboard and swipe navigation, an overview grid (`O`), a metro-line
map of where you are, print to PDF one slide per page, and a scrolling layout on phones.

Slides: title, executive summary, three scorecards with an "in a nutshell" line, deep dives (flow, responsiveness,
contributors, adoption, code, quality, themes), an improvement plan (overview plus one slide per priority with issue,
outcome, first actions and a target for the next edition), and appendices (method, all indicators).

## Indicators

Each one compares the last 90 days with the 90 before.

| Family | Indicators |
|---|---|
| Community & flow | issues opened/closed, net backlog, backlog age, median/p90 maintainer first response, **share answered within 7 days**, open issues with no maintainer reply, PR merge rate (all / external), time to merge (all / external), stale PRs, external PR share, new contributors, **top-merger share** |
| Adoption & reach | new stars, new forks, forks with their own pushes, PyPI downloads (platform and Python split), releases (GitHub and PyPI), days since release, HF Spaces (optional search proxy), dependents |
| Codebase & quality | commits, authors, **bus factor**, top-committer share, single-owner modules, lines changed per module, hotspot files, CI pass rate (main / PRs), CI duration, test/source LOC, critical deps behind PyPI or without an upper bound |
| Issue themes | type mix (bug / enhancement / question), theme counts with intervals, pain map (new, open, age at close) |

Statuses (on track / watch / at risk) come from `thresholds` in the config. Each change is coloured by whether the move
is good, bad or neutral for the project.

## Issue triage: chosen by measurement

`repo-pulse bakeoff` scores every candidate classifier on a gold set split into calibration and test halves. It fits
temperature scaling and an abstain threshold on the calibration split, then reports on the held-out test split:
accuracy, macro-F1, ECE, Brier score, coverage at 85% precision, speed and cost per 1,000 issues
(`out/<name>-bakeoff.html`).

- **Decision rule:** among candidates within 3 F1 points of the best with ECE ≤ 0.1, pick the lowest API cost, then the
  highest coverage at the target precision, then the fastest.
- **Gate:** macro-F1 ≥ 0.7 and ECE ≤ 0.1. Theme labels from a model that misses the gate are never counted; those issues
  show as "unclassified". Gold-set issues use their gold label. The deck always shows where labels came from.

On the repos tested so far, the issue-type model (ModernBERT, local) passed every time. For themes, TypeSafe Jev passed
on every repo (F1 0.72–0.83); the best free local model passed on one of five (F1 0.54–0.77). Zero-shot models scored
0.05–0.35 and are not worth running.

Which model is used is a policy set per config (`classifier:`; override with `--classifier`):

| Mode | Selects from | Cost |
|---|---|---|
| `local` (default) | free local models only | 0 |
| `auto` | every measured model, by the decision rule | ~$0.05 / 1k issues with Jev |
| `jev` | TypeSafe Jev for both fields | ~$0.05 / 1k issues |

Jev needs `TYPESAFE_API_KEY` in the gitignored `.env` and answers both questions in one call per issue. Switching modes
re-decides from the recorded bake-off; no re-run needed.

**Gold labels** are pre-labelled once by an LLM and are not authoritative until a maintainer reviews them: open
`out/<name>-gold-review.html`, correct and confirm, export, then `repo-pulse gold --import reviewed.json` and re-run the
bake-off.

## Narrative and grounding

Narrative sources, in priority order:

1. `data/<repo>/narrative-input-<date>.json`, written by an agent or a person from the digest
2. Without an agent: one API call over the ~2k-token digest, if `ANTHROPIC_API_KEY` is set in `.env`
3. Deterministic rules

Every claim cites metric keys. `llm/validate.py` drops any claim containing a number that cannot be derived from the
cited metrics (value, prior, delta, percent change or ratio). Known limit: the check is numeric, not semantic, so a real
number attached to the wrong description can still pass. Plan targets are goals and are not number-checked.

## Scheduled editions

After a repo's first edition (taxonomy and gold set, with a human in the loop), later editions can run from cron:

```bash
# every Monday 06:00
0 6 * * 1  cd /path/to/repo-pulse && AGENT=codex scripts/run-edition.sh configs/<name>.yaml >> logs/cron.log 2>&1
```

`scripts/run-edition.sh` runs collect → classify → analyze itself (0 tokens), writes the digest and calls the agent with
[`tasks/edition.md`](../tasks/edition.md), whose only job is the narrative and plan. The script then rejects the run if
the agent touched `src/`, `configs/` or gold labels, re-validates the narrative (no dropped claims allowed), builds the
deck and runs the layout check. Outputs: the deck, a 5-line summary and a log.

| `AGENT` | Command used | Notes |
|---|---|---|
| `codex` | `codex exec --sandbox workspace-write` | tested: ~2 min, no dropped claims |
| `pi` | `pi -p --no-session -nc --tools read,write,edit,bash` | pass a capable model via `AGENT_ARGS="--model …"` |
| `claude` | `claude -p --permission-mode acceptEdits` with an allowlist | |
| `none` | no agent | rule-based narrative; dry run of everything else |

## Example decks

`docs/examples/` holds published examples, built with names replaced by roles:

```bash
uv run repo-pulse -c configs/trl.yaml --as-of 2026-10-06 build --anonymize \
  --note "Example snapshot as of 2026-10-06, …" --out docs/examples/trl.html
```

`--anonymize` replaces GitHub logins and git author names with roles (maintainer A, contributor 1, author 1) everywhere
in the deck. GitHub Pages serves `docs/` at https://charlespoisson.com/repo-pulse/, with `docs/index.html` as the landing page.

## Token budget

- Issue triage: 0 tokens with local models (only new or edited issues are re-scored), or ~$0.05 per 1,000 issues with Jev.
- Narrative: one ~2k-token digest read per edition, or one API call of about 2k in and 2.5k out.
- Gold set: a one-time LLM pre-labelling pass, then human review.

## Caveats

- **Stars:** GitHub often returns no stargazer history to a user token, so "new stars" can be blank on a first edition.
  Exact snapshots accumulate from then on; a repo's own committed star-history SVG can be decoded as an approximation
  (`star_history_svg`).
- **PyPI:** pypistats keeps about 180 days, so a young package's prior window can be partly covered.
- **Code health** metrics (test/source LOC, module tests) are Python-centric.
- **HF Spaces and dependents** are best-effort proxies.

## Development

```bash
uv run --group dev pytest
```

[`AGENTS.md`](../AGENTS.md) is the guide for agents (and people) changing the tool itself: layout, invariants and how to
verify a change.

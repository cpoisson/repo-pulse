---
name: repo-pulse
description: Build an analytic executive-summary slide deck on the health of any public GitHub repository, for the maintainers who steer it — 90-day vs prior-90-day indicators (issue/PR flow, maintainer responsiveness, contributors, bus factor, adoption, CI and dependency risk, issue themes) plus a prioritized, outcome-driven improvement plan. Use this skill whenever someone asks how an open-source project is doing, wants a repo health check, project pulse, maintainer report, quarterly OSS review, community/contributor analysis, issue triage themes, or "an exec summary / deck about repo X" — even if they don't say "deck" or name this tool.
---

# repo-pulse

Turns a public GitHub repo (or a gitlab.com project, `forge: gitlab`) into a self-contained 16:9 HTML deck (one file, offline, print-to-PDF ready) for its maintainers.
The tool is the repository this skill ships in (github.com/cpoisson/repo-pulse); this file is the playbook for *running*
an analysis. The skill may be installed on its own (for example with `npx skills add cpoisson/repo-pulse`), so the setup
step below finds or clones the tool first. It works with any coding agent that can run shell commands and edit files: the steps that need judgment
(taxonomy, gold labels, narrative) produce plain files, so no specific model or vendor API is required.
To *change the tool itself*, read `AGENTS.md` at the repo root instead.

## Principles (why the workflow looks like this)

- **Numbers are computed, never written.** Metrics are deterministic Python over GitHub/git/PyPI data. You interpret; you
  never compute a figure in prose. The validator deletes narrative claims whose numbers don't match the metrics they cite.
- **Models are chosen by measurement, not by model card.** The issue classifier is picked by a bake-off on a labelled
  gold set with calibration (ECE) and an accuracy gate. If no model passes, the deck says so instead of showing weak themes.
- **Token-efficient by design.** Triage runs local models (0 tokens) by default. The only agent/LLM work is a one-time gold
  pre-label pass and one narrative per edition over a ~2k-token digest of aggregates — done by you, the running agent.
- **Honest about provenance.** Approximations (star history, partial PyPI coverage, unreviewed gold labels) are flagged
  on the slide where they matter.

## Setup (once)

Needs `git`, [uv](https://docs.astral.sh/uv/) and an authenticated [GitHub CLI](https://cli.github.com/) (`gh auth status`).
Use the current directory if it is a repo-pulse checkout, else `$REPO_PULSE_HOME`, else `~/.local/share/repo-pulse`
(clone it there if missing):

```bash
if [ -f src/repo_pulse/cli.py ]; then RP=$PWD; else RP=${REPO_PULSE_HOME:-$HOME/.local/share/repo-pulse}; fi
[ -d "$RP/.git" ] || git clone https://github.com/cpoisson/repo-pulse "$RP"
cd "$RP" && git pull --ff-only -q || true
uv sync --extra local-models
```

Run every command below from `$RP`. `C=configs/<name>.yaml`; `--as-of` defaults to today. Configs, data and decks stay
in that checkout (`configs/`, `data/`, `out/`, all gitignored), so later editions find the earlier ones.

## Workflow

### 1. Init and collect
```bash
uv run repo-pulse init owner/name            # or https://gitlab.com/group/project; clones to $REPO_PULSE_CLONES (default ~/.cache/repo-pulse/clones), writes configs/<name>.yaml
uv run repo-pulse -c $C collect              # issues, PRs, reviews, stars, forks, releases, CI runs, git, PyPI
```
Open the config and sanity-check it (`configs/_template.yaml` documents every field; keep machine-specific paths out): the `modules` map (prefix → module, longest prefix wins) should name the parts
maintainers think in; check `distribution` lists the channels users actually install from (PyPI, npm, crates.io, Docker
Hub images, GitHub release binaries; `init` infers them but cannot see images pushed from outside the repo, and registries
such as gcr.io or the Go proxy publish no counts); set `ci_workflow` if the repo has several push workflows; add `known_incidents` you learn about;
`backend_registry` (`path`, regex `pattern` with one group, `label`) only if the project has a plugin/backend registry.
If a collector fails the run continues — note what is missing rather than inventing it.

### 2. Propose the issue-theme taxonomy
```bash
uv run repo-pulse -c $C issues --chars 160 > /tmp/issues.txt   # read it (in chunks if long)
```
Write 8–13 themes into `themes:` (snake_case key → one-sentence description; always include `other`). Base them on what
the issues are actually about in this repo — areas maintainers would assign ownership to — not on a generic list.
Descriptions double as zero-shot label text, so make them concrete and mutually exclusive. State the taxonomy to the
user in one line and continue unless they object.

### 3. Gold set (one-time LLM pre-label, then human review)
Label up to ~250 issues yourself (all of them if fewer): one line per issue, `<number> <type> <theme>`, `-` to exclude
(withdrawn/spam). Read the full issue list, not a sample — a stratified-by-time list is fine for very large trackers.
```bash
uv run repo-pulse -c $C gold --prelabels /tmp/prelabels.txt     # also writes out/<name>-gold-review.html
```
Tell the user the labels are unreviewed and that `out/<name>-gold-review.html` → export → `gold --import reviewed.json`
makes them authoritative; the deck flags themes as provisional until then.

### 4. Bake-off and classification
```bash
uv run repo-pulse -c $C bakeoff --models rules,ModernBERT-base_issue-type,bge-small-en-v1.5+LR,bge-base-en-v1.5+LR,bge-base-en-v1.5+rules+LR,gliclass-edge-v3.0,typesafe-jev
uv run repo-pulse -c $C classify && uv run repo-pulse -c $C analyze
```
The config's `classifier` setting decides what may be selected (switching it never needs a new bake-off; `classify`
re-decides from the recorded results, and `--classifier` overrides it per run):
- `local` (default): free local models only; API models are not even run. ModernBERT usually passes for type; themes
  usually fail the gate, so themes come from gold labels only.
- `auto`: every measured model competes, including TypeSafe Jev when `TYPESAFE_API_KEY` is in `.env` (never paste keys in
  chat). On three tested repos Jev won both fields and was the only theme model to pass the gate (type F1
  0.76–0.90, theme F1 0.73–0.75, ECE ≤ 0.085) for about $0.05 per 1k issues, one call per issue.
- `jev`: force Jev for both fields (the gate is still reported).
Respect the user's choice; suggest `auto` only when themes matter and they are fine with a few cents of API spend.
(SetFit and the larger zero-shot models are slow and lost on every repo; skip them.) Report the selected models and whether each gate
passed; never loosen the gate to make a slide appear. `out/<name>-bakeoff.html` holds the full comparison.

### 5. Narrative
Write it yourself from the digest (the default, works for any agent). Optionally, if `ANTHROPIC_API_KEY` is set and there
is no narrative file, `narrate` makes one API call instead.
```bash
uv run repo-pulse -c $C digest          # the same ~2k-token digest the API call would see
```
Write `data/<owner>__<name>/narrative-input-<as_of>.json` following `references/narrative.md` (schema, writing rules,
worked example; set `author` to the agent/model that wrote it), then `uv run repo-pulse -c $C narrate`. Read the "dropped" lines it prints: each is a claim whose
numbers didn't match its cited metrics — fix the claim (usually: cite the right metric) rather than deleting the check.

### 6. Build and verify the deck
```bash
uv run repo-pulse -c $C build
uvx --with playwright python skills/repo-pulse/scripts/check_deck.py out/<name>-pulse-<as_of>.html
```
The check renders every slide at 1440×900 (light) and 1280×720 (dark) plus a phone pass, prints overflow warnings and
JS errors, and saves screenshots. Look at the summary, one scorecard, one deep dive and one plan slide. If a slide
overflows, shorten that narrative text first; only touch `deck.js`/`template.html` for structural problems.

### 7. Deliver
`open` the deck, then tell the user in a few lines: the headline, the top 3 findings, the P1–P3 plan items, and what is
provisional (unreviewed gold labels, approximate stars, failed theme gate). Mention `out/<name>-bakeoff.html` and
`out/<name>-gold-review.html`. Offer, don't force, publishing it as a shareable page.

## Deck anatomy (what the generator produces)

Title → Executive summary → 3 scorecard slides (each opens with an "in a nutshell" line and improving/worsening/at-risk
counters) → deep dives (flow, responsiveness, contributors, adoption, code, quality, themes) → improvement-plan overview
→ one slide per priority (issue · outcome · first actions · now vs target) → appendix (method, all indicators).
A metro-line map on every slide after the title shows where the reader is; `O` toggles an overview grid.

## Later editions

Scheduled: `scripts/run-edition.sh configs/<name>.yaml` (cron-friendly; `AGENT=pi|codex|claude|none`). It runs the
deterministic steps itself and hands an unattended agent `tasks/edition.md`, whose only job is the narrative.
By hand: re-run steps 1 (collect only), 4 (classify/analyze), 5 and 6 with a new `--as-of`. The previous edition's targets are
carried onto the plan slide automatically; write the new plan against them. Re-run the bake-off only when the taxonomy
or the gold set changes.

## Known limits

- Code-health metrics (test/source LOC) are Python-centric; for Rust/JS-heavy repos say so rather than reading much into them.
- Stars: GitHub no longer lists stargazers (404 with a token, 401 without, for every repo as of 2026-10), and GH Archive
  star events collapsed in 2026, so "new stars" is blank on a first edition; exact snapshots accumulate in
  `data/history/` and give exact window counts once one predates the window. The same applies to Docker Hub pulls and
  release-binary downloads, which only publish totals.
  For repos that commit their own star-history SVG, set `star_history_svg` to decode an approximate trend.
- Releases count GitHub Releases and PyPI uploads (many projects only tag + publish to PyPI).
- Download KPIs appear only for configured `distribution` channels; a project with none shows no download figure.
- Quiet repos are a valid result: empty windows render as "nothing in this window", and the narrative should say
  plainly that activity stopped (and ask whether the project is maintained) rather than hunting for a trend.
- Without Jev, local theme classifiers miss the gate at ~150–280 gold issues and 12–13 themes; the deck then uses gold
  labels (flagged provisional) and new issues stay unthemed. Gate results measure agreement with the gold labels — until a
  maintainer reviews them, that is agreement with the LLM pre-labeller, not ground truth.
- Only issues are themed; PRs feed flow and contributor metrics.
- GitLab (`forge: gitlab`): issues and MRs cover the lookback span plus everything open (each human author's earliest
  earlier MR is added for new-contributor dates); CI is default-branch pipelines only; no close reason, watchers or
  dependents. List the project's bot accounts in `bots:` (GitLab bots rarely end in `[bot]`).

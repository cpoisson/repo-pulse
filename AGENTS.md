# AGENTS.md — developing and maintaining repo-pulse

This file is for agents changing **this codebase**. Two other entry points exist for other jobs:

| Job | File | Reader |
|---|---|---|
| Run an analysis interactively (first edition: taxonomy, gold labels, narrative) | `skills/repo-pulse/SKILL.md` | any coding agent with a human around |
| Scheduled edition of an already-configured repo | `scripts/run-edition.sh` → prompt `tasks/edition.md` | an unattended agent (pi, codex, claude) |
| Change the tool | this file | agents developing repo-pulse |

repo-pulse turns a public GitHub or GitLab repo into a self-contained 16:9 HTML deck for its maintainers: deterministic
90-day-vs-prior metrics, a measured issue classifier, a number-checked narrative, and a prioritized improvement plan.

## Setup and checks

```bash
uv sync --extra local-models            # Python 3.12, uv; add --extra typesafe for the Jev classifier
uv run --group dev pytest               # must stay green
uv run repo-pulse --help
```

`gh` must be authenticated for `collect`. Analysed repos are local: `configs/<name>.yaml` (except `_template.yaml`) and
all of `data/` are gitignored, so a fresh clone has no deck to rebuild. To get one, configure any small public repo:

```bash
uv run repo-pulse init owner/name                    # or a gitlab.com URL; writes configs/<name>.yaml; a repo with a few hundred issues takes ~1 min
C=configs/<name>.yaml
uv run repo-pulse -c $C collect && uv run repo-pulse -c $C analyze && uv run repo-pulse -c $C narrate && uv run repo-pulse -c $C build
uvx --with playwright python skills/repo-pulse/scripts/check_deck.py out/<name>-pulse-<date>.html
```

`docs/examples/` holds published example decks built with `build --anonymize`; never commit a non-anonymized deck there.
Video and GIF slides are captured only from those decks (`media/video/scripts/capture.py`), never from `out/`.
After any change to `src/repo_pulse/deck/`, run `check_deck.py` on every deck you can build; it must report 0 issues
(no overflow, no JS errors, no horizontal scroll on phones).

## Layout

```
src/repo_pulse/
  cli.py           commands: init collect issues gold bakeoff classify analyze digest narrate build all
  config.py        Config dataclass; everything repo-specific comes from configs/<name>.yaml
  init.py          clone + infer module map / PyPI package / deps → starter config
  collect/         github.py (gh GraphQL/REST), gitlab.py (REST + GraphQL notes, same record shapes), git_local.py, pypi.py, distribution.py (npm, crates.io, Docker Hub, release assets), hfhub.py; cache.py = data/raw/<slug>/<date>/
  metrics/         flow, adoption, code, themes → metrics-<date>.json (kpi() records: key, label, value, prior, unit, status, direction)
  classify/        models.py (candidates), bakeoff.py (measure + decide), calibration.py, gold.py, run.py (production labels), report.py
  llm/             narrate.py (file > optional API > rules), validate.py (number grounding)
  deck/            template.html + deck.js (no dependencies) + build.py → out/<name>-pulse-<date>.html
configs/           _template.yaml (documents every field); per-repo configs are local and gitignored
data/<owner>__<name>/  local (gitignored) decision artifacts: gold.json, bakeoff.json, classifier.json, metrics, narrative inputs
skills/repo-pulse/ the run playbook (SKILL.md), narrative reference, deck checker
docs/              guide.md (user guide), adr/ (decision records), examples/ (anonymized decks)
```

## Invariants — do not break these

1. **Numbers are computed, never written.** Metrics are pure functions of raw data. Narrative text (from any agent or API)
   only passes if every number matches a cited metric (`llm/validate.py`). Never weaken the validator to make text pass;
   fix the text or the citation. `tests/test_validate.py` pins this behaviour, including its known limit.
2. **Classifiers are chosen by measurement.** Selection goes through `bakeoff.decide()` and the gate in the config.
   `classifier: local` (the default) must never run or select an API model. Don't hard-code a model choice.
3. **Generic core.** No repository-specific logic in `src/`: module maps, taxonomies, registries, incidents and thresholds
   belong in `configs/`. If a repo needs special handling, add a config field with a safe default and document it in
   `configs/_template.yaml` (`tests/test_config.py` checks this). No analysed repo's name, config or data is committed here.
4. **Self-contained deck.** One HTML file, no network requests, fixed 1280×720 canvas, readable in light/dark and on phones.
   Charts are hand-written SVG in `deck.js`; keep it dependency-free.
5. **Honest provenance.** Approximate or missing data is labelled on the slide (`note` on the KPI), not hidden or guessed.
   Empty windows render an explicit empty state.
6. **Secrets.** API keys live only in the gitignored `.env` (loaded by the CLI). Never commit, print or log them.

## Common changes

- **Changing what an indicator means** (definition, weighting, data source): record it as an ADR in `docs/adr/`
  (context, decision, alternatives turned down, consequences) and add it to the index there.
- **New KPI:** add a `kpi(...)` in the right `metrics/*.py`; set `lower_is_better` or add the key to `GOOD_UP` in
  `metrics/__init__.py` (otherwise it renders as neutral); add a threshold in the configs if it should get a status chip;
  put it in a deck slide or `SCORECARD` in `deck/build.py` if it matters to maintainers; add a test in `tests/test_metrics.py`.
- **New classifier candidate:** subclass `Base` in `classify/models.py` (`score()` for zero-shot or `fit_predict()` for
  supervised; set `api = True` if it calls a paid service), register it in `registry()`, and run the bake-off on the
  repos you have configured. Report results; do not change the gate.
- **Deck slide or layout:** edit `deck/deck.js` / `deck/template.html`, rebuild every available deck, run `check_deck.py`,
  and look at the screenshots of the slides you touched.
- **Unattended runs:** `tasks/edition.md` is the only prompt an unattended agent sees; keep it short, decision-complete
  (no questions) and limited to writing the narrative. Anything deterministic belongs in `scripts/run-edition.sh`, which
  also guards protected paths and re-validates the agent's output. Test changes with `AGENT=none` first.
- **New data source:** a collector in `collect/` behind `step(...)` in `collect/__init__.py` (a failing source must not
  abort the run), then metrics that tolerate its absence.

## Conventions

- Match the surrounding code: small pure functions, type hints, comments only where the *why* is not obvious.
- Prefer the standard library and existing dependencies; justify any new one.
- Commit messages describe the change; no agent attribution trailers or tool mentions.
- Generated outputs (`out/`, `data/`, per-repo configs, `.env`) stay out of git.

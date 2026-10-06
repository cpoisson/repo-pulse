# repo-pulse

[![repo-pulse: from a GitHub repo to a maintainer deck](docs/repo-pulse.gif)](https://charlespoisson.com/repo-pulse/)

**Know where your open-source project stands, and what to do next.**

repo-pulse turns any public GitHub repository into a short slide deck for its maintainers.
**[See example decks →](https://charlespoisson.com/repo-pulse/)**

## What you get

- **A clear picture in five minutes:** issue and PR flow, responsiveness, contributors, adoption, code health and what
  people report about, each compared with the previous 90 days.
- **A plan, not just charts:** three to five priorities, each with the problem, the expected outcome, first actions and
  a target to check in the next edition.
- **Numbers you can trust:** every figure is computed from GitHub, git and PyPI data, and any claim in the story that
  doesn't match the data is removed.
- **Cheap to run:** issues are sorted into themes by free local models (or an optional cheap one, if it measures better
  on your repo), and the story is written from a ~2k-token summary.
- **One file to share:** an offline HTML deck you can present, send or print to PDF.

See it on real projects: [TRL](https://charlespoisson.com/repo-pulse/examples/trl.html) ·
[LeRobot](https://charlespoisson.com/repo-pulse/examples/lerobot.html) ·
[speech-to-speech](https://charlespoisson.com/repo-pulse/examples/speech-to-speech.html).

## How it works

```
 Collect          Measure            Classify             Narrate              Deck
 GitHub, git,  →  90 days vs the  →  issue themes, by  →  story + plan,     →  one HTML
 PyPI             90 before          a model chosen       every number         file
                                     by measurement       checked
```

Python does all the counting. An agent (or you) only writes the story and the plan, and a validator checks every number
it cites against the data.

## Use it

You need [uv](https://docs.astral.sh/uv/) and the [GitHub CLI](https://cli.github.com/) (`gh auth login`).

**With a coding agent.** Install the skill; it works with any agent that supports
[skills](https://skills.sh) (Claude Code, Codex, Cursor, Copilot, Gemini…):

```bash
npx skills add cpoisson/repo-pulse
```

Then ask your agent:

```text
Make a repo-pulse health deck for <owner/repo>, then give me the headline,
the top 3 findings and the plan.
```

On first use the skill clones the tool to `~/.local/share/repo-pulse` (or `$REPO_PULSE_HOME`). Without the installer,
copy [`skills/repo-pulse/`](skills/repo-pulse) into your agent's skills folder, or paste this instead:
"Clone https://github.com/cpoisson/repo-pulse and follow skills/repo-pulse/SKILL.md to build a health deck for
<owner/repo>."

**By hand:**

```bash
git clone https://github.com/cpoisson/repo-pulse && cd repo-pulse
uv sync --extra local-models
uv run repo-pulse init owner/repo          # writes configs/repo.yaml
uv run repo-pulse -c configs/repo.yaml all # collect → classify → analyze → narrate → build
open out/repo-pulse-*.html
```

The quick path builds a deck without issue themes and with a rule-based story. For themes and a written narrative, follow
the [skill](skills/repo-pulse/SKILL.md). Later editions can run unattended from cron (see the guide).

## Learn more

- [Guide](docs/guide.md): commands, indicators, how the classifier is chosen, scheduled runs, caveats.
- [Skill](skills/repo-pulse/SKILL.md): the step-by-step playbook for running an analysis.
- [AGENTS.md](AGENTS.md): for changing the tool itself.

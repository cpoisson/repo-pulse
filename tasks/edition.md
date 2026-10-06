# Task: write the narrative for one repo-pulse edition (unattended)

You are running **unattended** (scheduled job). Nobody will answer questions: decide, act, and finish.
Working directory: the repo-pulse checkout. Edition: config `{{CONFIG}}`, as-of `{{AS_OF}}`, repo `{{REPO}}`.

The deterministic pipeline has already run (collect → classify → analyze). Your only job is the part that needs
judgment: the narrative and improvement plan. Everything else is checked by the wrapper after you exit.

## Do exactly this

1. Read the metrics digest: `{{DIGEST_FILE}}` (already generated; do not recompute anything).
2. Read the narrative format and rules: `skills/repo-pulse/references/narrative.md`.
3. If a previous narrative exists (`{{PREVIOUS_NARRATIVE}}`, may be "none"), read it: keep the same voice, and judge each of
   its plan targets against the new numbers (met / not met / no longer relevant) in the relevant `so_what` or plan items.
4. Write `{{NARRATIVE_FILE}}` (JSON, schema in the reference). Set `"author"` to your agent and model name.
5. Validate: `uv run repo-pulse -c {{CONFIG}} --as-of {{AS_OF}} narrate`
   Read every `dropped` line. Each means a number in your text is not supported by the metrics it cites: fix the claim
   or its `metrics` list and re-run. Repeat until it prints `dropped 0` (at most 3 attempts).
6. Write a 5-line plain-text summary to `{{SUMMARY_FILE}}`: headline, top finding, P1, what changed since the previous
   edition, and anything provisional.

## Rules

- Use only numbers from the digest; never compute new figures. Cite metric keys for every factual sentence.
- Plan: 3–5 items, ordered by impact × urgency, each with issue, outcome, 2–4 first actions, owner (role), effort,
  horizon and a plain-language target. Carry forward unmet targets from the previous edition rather than inventing
  new priorities, unless the data clearly moved.
- If the window is quiet (few issues/PRs/commits), say so plainly; do not hunt for trends in tiny numbers.
- Touch nothing except `{{NARRATIVE_FILE}}` and `{{SUMMARY_FILE}}`: no code, configs, gold labels or git operations.
  The wrapper rejects the run if anything else under `src/`, `configs/` or `data/*/gold.json` changed.
- Do not print or read `.env`.
- Finish in one pass; when step 5 shows `dropped 0` and step 6 is written, stop.

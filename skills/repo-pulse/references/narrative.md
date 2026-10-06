# Narrative file: schema, rules, example

File: `data/<owner>__<name>/narrative-input-<as_of>.json`. It is validated exactly like an LLM response.

## Rules that keep it trustworthy

- Every factual sentence carries a `metrics` list of KPI keys (as printed by `repo-pulse digest`). Every number in
  `text`, `issue`, `so_what` and nutshell `text` must be the value, prior, delta, a percent change or ratio of a cited
  metric, a number in its label/note, or an issue/version number from the digest context. Anything else is dropped.
- Goals are not facts: `outcome`, `actions` and `target` are proposals and are not number-checked — keep them concrete.
- Slide titles are assertions ("Replies are fast when they happen, but most issues wait over a week"), not topics.
- Lead with what a maintainer can act on. Be candid; no hype words; no restating every number on the slide.
- Mention a person only by the role or the login that already appears in the metrics.
- Keep text short enough for a 1280×720 slide: titles ≤ 75 chars, so_what ≤ 160, nutshell ≤ 220, plan issue ≤ 230.

## Schema

```json
{
 "author": "who wrote it (shown in the deck)",
 "headline": "one sentence for the title slide", "headline_metrics": ["key"],
 "summary_title": "assertion for the executive summary",
 "findings": [{"text": "…", "metrics": ["key"], "severity": "high|medium|low"}],          // exactly 3
 "nutshells": {"flow": {"text": "…", "metrics": []}, "adoption": {…}, "code": {…}},       // scorecard slides
 "slides": {"flow|responsiveness|contributors|adoption|code|quality|themes":
            {"title": "assertion", "so_what": "one or two sentences", "metrics": ["key"]}},
 "recs_title": "Improvement plan proposal",
 "recommendations": [                                                                      // 3–5, ordered
   {"priority": 1, "text": "imperative action title",
    "issue": "the problem with its evidence numbers", "outcome": "what changes for the project when this works",
    "actions": ["2–4 concrete first steps"], "owner": "role", "effort": "S|M|L",
    "horizon": "2 weeks|this quarter|next quarter",
    "target": "plain-language measurable target for the next edition", "metrics": ["key"]}]
}
```

Priority = impact on project health × urgency; P1 addresses the highest-severity finding. Each plan item should move a
metric that appears in its `metrics`, so the next edition can check it.

## Worked example (a real edition, repository anonymized, abridged)

```json
{
 "headline": "Reach and contributions multiplied this quarter, but one maintainer now handles 95% of merges.",
 "headline_metrics": ["top_merger_share"],
 "findings": [
  {"text": "Merging is a single point of failure and it is getting worse: one maintainer performed 95% of merges (71% in the prior window), bus factor is 1 and the top committer wrote 72% of commits.",
   "metrics": ["top_merger_share", "bus_factor", "top_committer_share"], "severity": "high"}],
 "nutshells": {"flow": {"text": "Contributions surged and the backlog shrank, but the community waits longer: only 21% of issues get a maintainer reply within 7 days and one person performs 95% of merges.",
   "metrics": ["response_within_7d", "top_merger_share"]}},
 "slides": {"responsiveness": {"title": "Replies are fast when they happen, but most community issues wait over a week",
   "so_what": "The median first maintainer reply is 0.9 days for issues that got one, yet only 21% were answered within 7 days.",
   "metrics": ["median_first_response_days", "response_within_7d"]}},
 "recommendations": [
  {"priority": 1, "text": "Name a second merger and split review ownership by module",
   "issue": "95% of merges went through one maintainer (71% prior), bus factor is 1 and 6 modules have one author with over 80% of commits.",
   "outcome": "Reviews and releases keep flowing when the lead maintainer is away.",
   "actions": ["Grant merge rights to a second maintainer", "Add CODEOWNERS per module", "Require one module-owner approval"],
   "owner": "lead maintainer", "effort": "M", "horizon": "this quarter",
   "target": "Under 70% of merges by one person; bus factor of 2 or more",
   "metrics": ["top_merger_share", "bus_factor", "modules_single_owner"]}]
}
```

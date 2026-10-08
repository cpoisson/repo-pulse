# 0001 · Weigh ownership metrics by code work, not commit count

- **Status:** Accepted
- **Date:** 2026-10-07
- **Issue:** [#1](https://github.com/cpoisson/repo-pulse/issues/1)

## Context

Bus factor, "top committer share" and single-owner modules counted every non-merge commit as 1. A typo fix in a README
weighed as much as a feature, and so did a one-line metric and a 1,300-line tool. Two Prysm PRs by the same author show
the gap: #17634 adds two metrics (4 files, +35 −5) and #17595 adds a new linter for the Bazel removal (18 files,
+1,330 −24). Squash-merged, each is one commit.

Measured on the cached repos (last 90 days), the commit count misread ownership:

- **TRL:** 32% of commits touch no source file (tests, CI, docs only). The top committer by count (275 commits) is
  second by code (143). The real first has 170.
- **LeRobot:** by commits, bus factor 3 and top share 38%. By code work, bus factor 2 and top share 42%, up from 19%.
  Counting commits hid a concentration.

The name "top committer share" also read as a ranking of people, when the indicator is about risk: how much of the
code work rests on one person.

## Decision

1. **Classify every changed file** as `code`, `tests`, `docs`, `build`, `deps` or `generated`.
   - Generic path rules are the default: lockfiles, CI directories, Bazel/Docker/Make files, test directories and
     `*_test.*`, Markdown and `docs/`.
   - Files that declare themselves generated are detected from the clone: the `generated … DO NOT EDIT` header
     convention and `linguist-generated` in `.gitattributes`.
   - A `path_kinds` config field overrides the defaults. Renames count only their changed lines.
2. **Weigh each commit by `log2(1 + lines changed)`**, per kind.
   - The two PRs above weigh about 5.1 and 10.4: the large one counts about twice, not once and not nearly 40 times.
   - Generated files, lockfiles and changelog fragments count for nobody.
3. **Compute ownership on code work only.**
   - The bus factor becomes the number of authors doing 50% of code work.
   - "Top committer share" becomes **code concentration** (key `code_concentration`, the top author's share of code
     work, lower is better).
   - Single-owner modules use the same weight.
   - The raw commit count stays as its own indicator.
4. **Read functional intent from changelog fragments, not from guesses.**
   - When a project has each PR add a fragment (`changelog_fragments`, detected by `init`), its sections give each
     commit's kind: `### Added` / `### Fixed` / … headings, or towncrier names such as `123.bugfix.md`.
   - This yields features, fixes, changes, removals and internal work per author, plus the KPIs `changes_features`,
     `changes_fixes` and `changelog_coverage`.
   - On Prysm, 100% of commits carry one. Without fragments there is no functional mix, and the deck does not infer one.
5. **Show the mix, not a score.** The contributors slide shows each author's share of the team's work, stacked by kind
   (code, tests, docs, build). The tooltip adds the functional mix.

## Alternatives considered

- **Raw lines changed.** Generated code dominates: one protobuf regeneration would outweigh a quarter of features. The
  log weight and the generated-file exclusion address this.
- **Conventional-commit prefixes (`feat:`, `fix:`) for functional intent.** Too rare to use: 6% of Prysm and 4% of
  TRL commits carry one.
- **Classifying PR titles into feature or fix.** Possible later. It must go through the bake-off and gate like the
  issue classifier (invariant 2), so it is not done by default.
- **Blast radius as a weight.** It is a separate axis from effort. A small change in a widely imported package (#17634
  touches `beacon-chain/blockchain`, imported by 29 packages) can be riskier than a large self-contained one (#17595
  mostly lives in `tools/prysm-vet`, imported by none). It is deferred, in this order of preference:
  1. critical paths declared in the config;
  2. breaking-change signals (`Removed`, `Deprecated`, changeset `major`);
  3. changes reverted or re-fixed within 14 days;
  4. import fan-in.

  Fan-in comes last because it is language-specific and misses build files and runtime coupling.
- **One "impact score" combining size, function and risk.** Rejected: opaque and arguable, against the "numbers are
  computed, provenance is honest" invariants. Each axis stays visible on its own.

## Consequences

- **Some indicators moved on existing decks.** LeRobot's bus factor dropped to 2. A repo whose recent commits touch no
  source code (smolagents) has no bus factor for the window and says so.
- **Narratives that cited "top committer … of commits" had to be rewritten.** The number validator caught the ones
  whose figures no longer matched.
- **The weight is a proxy.** Design, review and debugging don't show in lines changed. The KPI note says how work is
  counted, and the review and merge indicators on the flow slides complement it.
- **Repos with generated code under unusual paths need `path_kinds`.** The skill tells the running agent to check this.

# Architecture decision records

Short records of decisions that shape what repo-pulse measures or how it collects data: the context, what was decided,
the alternatives turned down and what follows from it. They explain *why* the code looks the way it does. The code and
`configs/_template.yaml` remain the reference for *what* it does.

| # | Decision | Status |
|---|---|---|
| [0001](0001-ownership-by-code-work.md) | Weigh ownership metrics by code work, not commit count | Accepted |

## Writing one

Add an ADR when a change alters the definition of an indicator, adds a data source, or turns down an obvious
alternative someone will propose again.
- Copy the sections of an existing record: Status, Context, Decision, Alternatives considered, Consequences.
- Number it sequentially and add it to the table above.
- Keep it to one page.

When a decision changes, don't rewrite the accepted ADR. Add a new one and mark the old one "Superseded by NNNN".

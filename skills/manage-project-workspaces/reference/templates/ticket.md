## Ticket — `Tickets/<number>-<Subject>.md`

The project key stays in `tickets:` and the heading; the file name carries only the number, so the subjects line up in a sorted list. `ACME-1234` → `Tickets/1234-NaturalSortAdApprovals.md`.

Current state. Budget: 250 words.

```markdown
---
type: ticket
status: active
tickets: [ACME-1234]
---

# ACME-1234 <short subject>

**Goal:** <one line>

**Status:** <one line — where it stands now>

## Findings

- <what was learned that outlives the ticket>

## Links

- Ticket: <url> · PR: <url>
- [[<RelatedResearchDecisionOrPlaybook>]]
```

## Spec — `Specs/<number>-<Subject>Spec.md`

The agreed plan for one piece of work, written before building and followed by it. It's named after its ticket note plus `Spec` (`ACME-1234` → `Specs/1234-NaturalSortAdApprovalsSpec.md`), so a link to the ticket note never resolves to the spec. Without a ticket: `Specs/<Subject>Spec.md`.

Current state — rewritten in place as the work moves. No word budget. **Required sections:** Problem, Acceptance criteria, Decisions, Out of scope, Open questions, Steps; lint reports a missing one.

| `status` | Meaning |
| --- | --- |
| `draft` | Not yet approved (saved so an interrupted session doesn't lose it) |
| `approved` | Agreed; the build follows `## Steps` |
| `built` | Built; `## Departures` and `## Review` are filled in |
| `in-review` | Its MR/PR is open; `request:` holds the link |
| `abandoned` | Dropped; kept until someone decides to delete it |

```markdown
---
type: spec
status: approved
tickets: [ACME-1234]
profile: <house-style profile, if one applies>
request: <MR/PR URL, once opened>
---

# ACME-1234 <short subject> — spec

## Problem

<what is wrong or missing, in the user's terms>

## Acceptance criteria

- <how we'll know it's done>

## Decisions

- <interfaces, seams, data shapes — no file paths; they rot>

## Out of scope

- <what this deliberately doesn't do>

## Open questions

<empty at approval>

## Steps

1. <one committable change> — **Done:** <the check that proves it>

## Departures

<steps revised, dropped or added during the build, and decisions made without the user>

## Review

<review findings left unfixed>
```

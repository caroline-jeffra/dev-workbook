## Thread — `Threads/<NounPhrase>.md`

Current state. Budget: 300 words. Done items collapse to one line each with no date or narrative; when nothing is open, set `status: done` and remove it from `## Next up`.

```markdown
---
type: thread
status: open
tickets: []
---

# <Thread name in sentence case>

**Goal:** <one line — what "finished" looks like>

## Open

- [ ] <action> — <one-line context if needed> ([ACME-123](url))

## Done

- [x] <action>
```

**Closing it** — when the last item is ticked, or the user says it is done or abandoned, follow "Closing a thread" in [structure.md](../structure.md): move decisions, durable knowledge and leftover items to their own notes, then reduce the thread to this stub.

```markdown
---
type: thread
status: done
closed: YYYY-MM-DD
---

# <Thread name in sentence case>

**Goal:** <the original goal>

**Outcome:** <one line — shipped, or abandoned and why>

**Moved to:** [[<DecisionNote>]], [[<Note>]], [[<OtherThread>]]
```

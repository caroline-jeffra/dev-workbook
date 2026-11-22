## Playbook — `Playbooks/<Area><Subject>.md`

Current state: the plan **and** its tracker. Tick steps in place as they finish; do not mirror them into a thread. `status: active` while being executed, `done` when finished, `reference` for a procedure you re-run (a setup guide, a cutover runbook).

~~~markdown
---
type: playbook
status: active
tickets: []
---

# <Subject in sentence case>

**Goal:** <one line — the outcome this playbook produces>

**Done when:** <checkable condition — a command that passes, a URL that serves, a state you can observe>

## Before you start

- <prerequisite or access needed>
- <decision to make first> — [[<DecisionNote>]] once made

## Steps

- [ ] **1. <Step title>** (~<estimate>) — <one line on what and why>
  - `<command>` or <sub-action>
- [ ] **2. <Step title>** (~<estimate>) — <one line>

## Verify

```bash
<the commands that prove "done when">
```

## Gotchas

- **<Trap>** — <how to avoid it>

## Out of scope

- <what this playbook deliberately does not do, and where it lives instead>
~~~

- **Steps are actions, not essays.** One line each; sub-bullets only for the commands or sub-actions needed to carry it out. Reasoning belongs in a linked decision or research note.
- **Decisions do not live in the playbook.** "Before you start" names them; once made, each becomes a decision note and the bullet links it.
- **No outcome narration on ticked steps.** `- [x] **3. Alembic init**` is complete. What happened goes in the day's log.

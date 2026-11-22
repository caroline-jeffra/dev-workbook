## Overview.md

Current state. Rewrite in place on every close-out so it is true today. Budget: 200 words.

```markdown
---
type: overview
status: active
---

# <repo>

**Repo path:** `<path relative to the code root>`

**Current focus:** <one line — what the work is right now>

## Next up

- ACME-1234 — [[1234-NaturalSortAdApprovals]] — awaiting review
- <non-ticket work> — [[<ThreadOrPlaybook>]]

## What this is

<Two or three sentences: what the codebase does, why the user is working on it.>

## Trackers

- Jira: <url or n/a>
- GitHub/GitLab: <url or n/a>

## Map

- [[<Workspace>/ProgressLog|ProgressLog]] · [[<Workspace>/TopicIndex|TopicIndex]] · [[<Workspace>/DecisionsIndex|DecisionsIndex]] · [[<Workspace>/ThreadsIndex|ThreadsIndex]]
```

`## Next up` says *which* tickets and threads are next, as pointers with no cap, most urgent first: `KEY — [[ticket note]]` plus at most a 2–3 word state such as "awaiting review"; non-ticket work points at its thread or playbook. A ticket's next step lives in its note's `**Next:**` line, not here. Remove a pointer the moment its ticket ships or closes.

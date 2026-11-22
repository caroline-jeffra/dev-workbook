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

- <the next concrete step> — [[<ThreadOrPlaybook>]]
- <at most five bullets, most urgent first; remove a bullet the moment it is done>

## What this is

<Two or three sentences: what the codebase does, why the user is working on it.>

## Trackers

- Jira: <url or n/a>
- GitHub/GitLab: <url or n/a>

## Map

- [[<Workspace>/ProgressLog|ProgressLog]] · [[<Workspace>/TopicIndex|TopicIndex]] · [[<Workspace>/DecisionsIndex|DecisionsIndex]] · [[<Workspace>/ThreadsIndex|ThreadsIndex]]
```

`## Next up` is **the only place next work is stated** in a workspace. Each bullet names one action and links the thread or playbook holding the detail.

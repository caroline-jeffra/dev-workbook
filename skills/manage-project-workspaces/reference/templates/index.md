## Index note (`Projects/WorkspaceIndex.md`)

Maps each repo to its workspace folder. Header + one row per repo:

```markdown
---
created: YYYY-MM-DD
tags: [index]
---

# Project Workspaces

| Repo path | Workspace |
|-----------|-----------|
| some-repo | [[SomeRepo/Overview]] |
| /opt/src/odd-one | [[OddOne/Overview]] |
```

The Workspace cell is a plain link to the workspace's `Overview` — never aliased, since an alias pipe splits the row in viewers that ignore the `\|` escape.

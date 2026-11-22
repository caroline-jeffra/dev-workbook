## `TasksArchive.md` (vault root — create once per vault)

Lives at `$DEVWB_VAULT/TasksArchive.md`, not inside a workspace. Seed it with the frontmatter and
intro only; months and rows get appended as work happens.

```markdown
---
created: <YYYY-MM-DD>
tags: [index, archive]
---

# Tasks archive

One line per working day, newest year first. This is the quick-reference for personal update meetings — scan a month, recall what you shipped.

Rows are deliberately **terse**: one short clause per project touched that day, three to four words each, at a very high level. No links inside table cells — the `Month's Projects` line above each table is where the project links live, and all detail lives in each project's `ProgressLog`.

# <YYYY>

## <Mon YYYY>

### Month's Projects
[[<project>/Overview|<project>]]

| Date | Tasks |
| ---- | ----- |
| <d>  | <one 3–4 word clause per project touched, comma-separated, no links> |
```

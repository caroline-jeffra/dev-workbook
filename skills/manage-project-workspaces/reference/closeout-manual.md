# Close-out by hand

Read this only when `dev-workbook closeout` is unavailable, exits non-zero or fails, as [closeout.md](closeout.md) says. It holds the mechanics the command does for you; what to write is in closeout.md.

Read the template for each file you write: [templates/log.md](templates/log.md) for the day's log, [templates/progress-log.md](templates/progress-log.md) for a `ProgressLog.md` line, [templates/tasks-archive.md](templates/tasks-archive.md) for a `TasksArchive.md` row or the file. For the log, also read the `The two-altitude` section of structure.md with `sed -n '/^## The two-altitude/,/^## /p' "<skill dir>/reference/structure.md"`.

## The day's log and its ProgressLog line

Write `Log/YYYY-MM-DD.md` (`type: log`, `date:` matching the filename) as **one** `Did` / `Decided` / `Learned` / `Links` block. If the day's note already exists, **merge into its sections** — never add a second block or a `###` sub-entry, and fix any earlier line the day's later work made wrong. Then add or update that day's one-line entry in the root `ProgressLog.md`, newest first.

## The TasksArchive layout

Newest year first (`# 2026`), and within it newest month first (`## Aug 2026`). Each month has a projects header above its table, then the table itself:

```markdown
## Aug 2026

### Month's Projects
[[harbor.example.com/Overview|harbor.example.com]], [[garden-planner/Overview|garden-planner]]

| Date | Tasks |
| ---- | ----- |
| 5    | ...   |
```

- **Exactly two columns** — `Date` and `Tasks`, nothing more. Never widen the table.
- **Date column** — the bare day number, nothing else. Days with no work get no row.
- **Month's Projects** — every project touched that month, most-active first. These are the only links that should point at a project `Overview`.
- **New month** → add a new `## <Mon YYYY>` section above the previous one, with its own projects header and table. Add the projects header entry the first time a project appears that month.

## Close-out sync by hand

- **`sync=self`** — when the user closes out the session run `dev-workbook maintain`, stage only the paths the plugin owns (`git -C "$DEVWB_VAULT" add -- Projects Resources Contributions Home.md TasksArchive.md WorkPlanning.md`, skipping any that do not exist), commit them as one single-line commit (`vault: session updates YYYY-MM-DD`) and push. Never `git add -A`, and never commit mid-merge or on a detached HEAD. If the push fails, leave the commit and tell the user.

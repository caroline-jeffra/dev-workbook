# Writing to the workspace

Applies to every write — logging progress, recording a decision or thread, closing out a session. If the workspace or a vault-level file is missing, read [scaffold.md](scaffold.md) first.

Read these sections of structure.md before writing, each with `sed -n '/^## <Heading>/,/^## /p' "<skill dir>/reference/structure.md"` (`<skill dir>` is this skill's base directory) rather than reading the whole file:

| Writing | `## <Heading>` to read (a prefix is enough) |
|---|---|
| Any note | `Two kinds`, `Writing style` |
| A new note, or a rename | `Naming` |
| A link | `Linking` |
| Frontmatter or a `status` | `Frontmatter` |
| Closing a thread | `Closing a thread` |
| Superseding a decision | `Superseding` |
| A log or its index line | `The two-altitude` |

The rest of the contract is in [structure.md](structure.md). Read the template file for each type you write, and only that one:

| Writing | Template |
|---|---|
| The day's log | [templates/log.md](templates/log.md) |
| A `ProgressLog.md` line | [templates/progress-log.md](templates/progress-log.md) |
| `Overview.md` | [templates/overview.md](templates/overview.md) |
| A thread, or closing one | [templates/thread.md](templates/thread.md) |
| A playbook | [templates/playbook.md](templates/playbook.md) |
| Research | [templates/research.md](templates/research.md) |
| A ticket note | [templates/ticket.md](templates/ticket.md) |
| A decision or convention | [templates/decision.md](templates/decision.md) |
| A note | [templates/note.md](templates/note.md) |
| A diagram | [templates/diagram.md](templates/diagram.md) |
| `TimeTracking.md` | [templates/time-tracking.md](templates/time-tracking.md) |
| A `TasksArchive.md` row, or the file | [templates/tasks-archive.md](templates/tasks-archive.md) |

## Step 4 — Write back (on trigger only)

This step runs only when one of the triggers in "When to log progress" below fires — an explicit request, or the user closing out the session. It is not something to do as work happens.

Golden rule: **never overwrite existing content.** Read the file, then append or edit in place. Create a file (with its header) only if it is absent.

### Write one note per fact

Follow the structure.md sections above. In short:

- **The day's log** — write `Log/YYYY-MM-DD.md` (`type: log`, `date:` matching the filename) as **one** `Did` / `Decided` / `Learned` / `Links` block. If the day's note already exists, **merge into its sections** — never add a second block or a `###` sub-entry, and fix any earlier line the day's later work made wrong. **No `Next:` line.** Then add or update that day's one-line entry in the root `ProgressLog.md`, newest first. Never append a dated entry to the root `ProgressLog.md` itself — it is an index.
- **Case-study flags** — reviews and interviews ask for specific examples, and the session is often the only record of the best ones. Before writing the log, check the session's work against the prompts in `$DEVWB_VAULT/Contributions/CaseStudyPrompts.md` (if the vault has none, read the bundled list at `<plugin root>/skills/summarize-contribution/reference/case-study-prompts.md`; do not create the vault copy from here). For each real match, add one line to the day's log: ``- **Case study:** <what happened, one clause> — `slug` `slug` · <success | failure | mixed>``.
  - **Tag every prompt it answers** — an incident can also be a mistake owned and an observability fix.
  - **Watch hardest for the `Commits: low` prompts**: a disagreement, pushback on scope, a mistake caught, an approach abandoned, someone unblocked. Git will not show them later; this line will.
  - **Flag failures as readily as successes**, including an AI tool (this one included) getting something wrong that the user caught. `pair` prompts want both.
  - **Do not flag routine work.** No match is the normal case. If the story's *why* needs more than a clause, it belongs in a decision or note — link that note from the line.
  - On a second close-out the same day, merge into the existing lines. Mention a new flag in the close-out report ("flagged a case-study candidate: scope-pushback"), without asking anything.
  `summarize-contribution` harvests these lines into the project's case studies.
- **A ticket note** — rewrite each touched ticket's `**Status:**` and `**Next:**` so both are true today: `**Next:**` is the one planned next step, on one line. A ticket's next step lives only there, never in the log.
- **Next up** — rewrite `Overview.md`'s `## Next up` as pointers, one per ticket or thread that is next, most urgent first and with no cap: `KEY — [[ticket note]]` plus at most a 2–3 word state, or a link to the thread or playbook for non-ticket work. Add, reorder, and remove a pointer when its ticket ships or closes. When the Overview you are editing still holds task text under `## Next up`, convert those bullets to pointers and move the task text into each ticket's `**Next:**` (the "bring it into the template" rule below).
- **A decision** — a **new note** in `Decisions/`, named for the decision as a PascalCase claim, with `type: decision`, `status: active`, `decided: YYYY-MM-DD`, and `tickets:`. Never append to a `Decisions.md` — in this layout that file does not exist and must not be created.
- **Superseding a decision** — when the new decision replaces an old one, **edit the old note**: set `status: superseded`, add `superseded_by:`, and put a `> [!warning]` callout under its heading. Add the matching `supersedes:` and `> [!note]` callout on the new one. Skipping this is the single failure this layout exists to prevent — both notes then read as current.
- **A thread** — one note per thread in `Threads/`, `type: thread`. Tick `- [x]` inside it as items finish — the item text stays one line, with no "done on <date>" or outcome narrative appended. When nothing is left — or the user says the thread is done or abandoned — **close it**: move its decisions, durable knowledge and leftover items to their own notes, then reduce it to the closing stub (`status: done`, `closed:`, Goal / Outcome / Moved to). See "Closing a thread" in [structure.md](structure.md).
- **A playbook** — an ordered procedure goes in `Playbooks/` as `<Area><Subject>.md` (no suffix), `type: playbook`. While it is being executed it is the tracker: tick its steps in place and do not open a thread that repeats them.
- **Overview** — update "current focus" when the direction of the work shifts.
- **Time tracking** — only if `TimeTracking.md` exists: measure the sittings since `tracked_through:` and update the table, per [time-tracking.md](time-tracking.md).
- **Names** — name each note by the pattern in the `Naming` section of structure.md, never by the project, the folder's type or a ticket key.

### Current-state notes are rewritten, not appended

Every note except a log is **current state** (the first structure.md section above says why). When the work changes one, **rewrite it in place so it is true today**: delete finished or wrong lines, do not annotate them ("~~X~~", "update:", "now done"). Git holds the history. When you touch a current-state note that already breaks its template, bring it into the template as part of the same edit.

**Removing something? Remove its references too.** When a decision is superseded, a thread closes or a note is deleted or renamed, grep the workspace for links and mentions of it and fix every current-state note that still points at it. Logs are history and keep their links.

Templates for every type, and the naming table, are in [templates.md](templates.md) (one file per type) and [structure.md](structure.md).

- **Never create** `Decisions.md`, `Open Threads.md`, or a dated section inside the root `ProgressLog.md`. Those are retired flat-layout files; creating them produces two contradictory sources of truth in one workspace.

**Do not hand-write `project:`, `topics:` or `tags:`.** The `vault-maintain` SessionEnd hook derives them and rewrites them anyway. Write `type`, `status`, the dates and the body; the hook fills in the rest and regenerates `TopicIndex.md` and `TicketsIndex.md` before the vault is committed. Write `topics:` explicitly only when you know the derived guess would be wrong — a hand-written list is respected.

**Never hand-edit `TopicIndex.md` or `TicketsIndex.md`.** They are generated; edits are lost.

### Links

Write every `[[wikilink]]` by the `Linking` section of structure.md: the shortest path that names exactly one note.

## When the vault contradicts these instructions

The vault is older than this skill and does not always match it. When they disagree, **say so in one line and keep going** — do not silently pick one, and do not stop and interrogate the user over something small.

- **Two workspaces claim the same repo** → write to the one in `WorkspaceIndex.md`'s main table; mention the trial exists. (Step 1.)
- **The superseded decision has no note** → record the replacement in prose, not frontmatter, and say you did. (See [structure.md](structure.md).)
- **An existing file breaks the format this skill documents** → if you are editing that note anyway, bring it into its template as part of the edit. Notes you are not touching are left for the `condense-vault` reconcile pass — do not sweep the workspace mid-task.
- **The workspace predates 2.0 names** (`Progress Log.md`, `Topic Index.md`, kebab-case or spaced note names) → read the old names, write new notes with the 2.0 names, and say once that the `condense-vault` reconcile pass will rename the rest. Do not rename on a logging pass.
- **A note carries frontmatter this contract does not list** → leave it, do not copy it forward.
- **The workspace is `status: paused` but the user is doing work in it** → log the work and ask whether to un-pause. Do not change project status on your own initiative.

Stop and ask only when writing would **destroy or contradict** something — never merely because the vault is untidy.

## Maintaining the TasksArchive

`$DEVWB_VAULT/TasksArchive.md` is the quick-reference the user scans before a personal update meeting: **one line per working day**, condensed enough to take in at a glance months later. It is the thin layer above the per-repo `ProgressLog.md` files, never a replacement for them.

**Append today's row when the session is closed out**, alongside the ProgressLog entry — on the same triggers as everything else in "When to log progress" below, never mid-session.

### Structure

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

### Writing a row

Rows are **terse by design** — the archive is scanned, not read. One short clause per project touched that day, **three to four words each**, comma-separated, at a very high level. The detail belongs in that project's `ProgressLog`; do not restage it here.

- Name the project when the clause needs the context (`garden-planner Phase 0 landed`), and carry a ticket number only where it *is* the shortest identifier (`ACME-1763 Laravel 13 planned`).
- Bold a genuine milestone — a release, an epic completing (`**ACME-1504 ready for review**`).
- Several projects in one day → one clause each, project named first so they stay separable.

**No links inside table cells.** A wikilink's alias pipe breaks the table row into phantom columns in viewers that ignore the `\|` escape, and the links crowd out the few words the cell is meant to carry. Project links belong in the `Month's Projects` line above the table, which is the one place they go.

Write it as a cell that renders in one line, e.g.:

```markdown
| 19 | ACME-1656 billing joins landed, garden-planner deployed |
| 12 | **ACME-1763 done — Laravel 10→13 climb complete** |
```

### Which day a session books under

Book work under the date it **started**. A session that runs past midnight still belongs to the day it began, so it appends to that day's row rather than opening a new one. If a row for the day already exists, extend it — never add a second row for the same date.

## Diagrams

- **Diagrams** — when the user asks for a diagram, or a note would be clearer with one, write it to `Diagrams/<Area><Subject>.md` as a Mermaid note and embed it where it's needed. When the Excalidraw plugin is in the vault and the user wants a drawing they can edit, write `Diagrams/<Area><Subject>.excalidraw.md` instead. Read an existing drawing through its `## Text Elements`; never rewrite one the user has edited.

## When to log progress

Progress logging is **not** continuous. Do not append ProgressLog entries, Decisions, thread updates, or TasksArchive rows mid-session as work happens — that noise interrupts the actual coding work. Write to the vault only on one of these two triggers:

- **The user explicitly asks** — "log progress", "record what we did", "record this decision", "update the vault", "note this down".
- **The user says to close out the session** — "close out the session", "wrap up", "we're done for the day", "end of session", or an equivalent.

When one of those fires, do the whole write in one pass: write or merge the day's log (with any case-study flags) and its ProgressLog line, rewrite `## Next up`, update threads (closing any that finished), playbooks and decisions as needed, update `TimeTracking.md` if the workspace has one, and append the day's row to [[TasksArchive]] (see "Maintaining the TasksArchive" above).

Keep each write incremental — the golden rule above ("never overwrite; append or edit in place") governs *how*.

## Close-out sync and background sessions

- **`sync=self`** — when the user closes out the session run `dev-workbook maintain`, stage only the paths the plugin owns (`git -C "$DEVWB_VAULT" add -- Projects Resources Contributions Home.md TasksArchive.md WorkPlanning.md`, skipping any that do not exist), commit them as one single-line commit (`vault: session updates YYYY-MM-DD`) and push. Never `git add -A`, and never commit mid-merge or on a detached HEAD. If the push fails, leave the commit and tell the user.

**Background sessions** (`background=yes`) never write a vault path directly — Claude Code blocks `Write`/`Edit` on the vault's checkout there. For each note you would create or change, run `dev-workbook stage "<vault-relative path>"` and read and write it at the path it prints. Stage each note once. The hooks merge staged notes into the vault three ways when the session ends, so edits made meanwhile survive; a conflicting edit stays staged and the next session reports it (`dev-workbook staged` lists them). Skip renames and deletions in a background session.

## Vault writing style

Write prose by the `Writing style` section of structure.md, which also holds the per-type length budgets.

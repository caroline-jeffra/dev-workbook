---
name: manage-project-workspaces
description: Maintains a per-repository workspace in the user's markdown vault (Obsidian, Foam, …) as the source of truth for ongoing development work — overview, dated progress log, decisions/ADRs, and open threads. Use when the user asks what to work on next or where a body of work stands — "what's the next task", "what should I work on", "where did we leave off", "what were we doing on this" — as well as "log progress", "record what we did", "record this decision", "track open threads", "close this thread", and — only on request — "set up time tracking", "how many hours has this phase taken". Consult this vault before an issue tracker (Jira/GitHub/GitLab) for next-work questions. Not for "what's the status" in the git sense — uncommitted changes, branch state and diffs come from git, not from here.
---

# Managing project workspaces

Keep a durable, per-repo workspace in the user's markdown vault (Obsidian, Foam, …) so ongoing development work has one
findable home — simpler than scattering context across ticket trackers, issues, and code comments.

**Vault location:** resolve in this order — (1) the `DEVWB_VAULT` environment variable (or the pre-3.0 `OBSIDIAN_VAULT`), (2) the config file `${XDG_CONFIG_HOME:-~/.config}/dev-workbook/vault` (or the pre-3.0 `…/claudesidion/vault`), (3) the legacy config file `~/.claude/obsidian-vault`, (4) the default `~/ObsidianVault`. A config file holds one line, the vault's path (whitespace trimmed, a leading `~/` or `$HOME/` expanded); `dev-workbook vault-path` prints the result. If none of them yields an existing directory, ask the user where their vault is and write the answer to `~/.config/dev-workbook/vault` (creating the folder) so every future session and hook finds it. Use the resolved absolute path (written below as `$DEVWB_VAULT`) for every read/write.

**Plugin tools** run through the `dev-workbook` command. If `command -v dev-workbook` finds nothing, run `python3 "<plugin root>/bin/dev-workbook"` instead — the plugin root is two levels above this skill's base directory. A skill installed on its own, outside the plugin, needs the command on PATH: `ln -s <plugin root>/bin/dev-workbook ~/.local/bin/`.

You typically run this skill while the user's working directory is *a different repo*. Always address
the vault by its absolute path; derive the current repo from the working directory, not the vault.

## Step 0 — Ensure the vault-level files exist (once per vault)

Two files live at the **vault root**, not inside any workspace:

- `$DEVWB_VAULT/Projects/WorkspaceIndex.md` — the repo → workspace map (see Step 1).
  A vault from before 2.0 has it as `Projects/_index.md`, and its archive as `Tasks Archive.md`:
  read and update the old file in place until `condense-vault` renames it. Never create the new
  name beside the old one.
- `$DEVWB_VAULT/TasksArchive.md` — the human-friendly day-by-day summary (see
  "Maintaining the TasksArchive" below). Create it from the template in
  [reference/templates.md](reference/templates.md).

**Ask before the first write to a vault that already has content in it.** A question like
"what should I work on" is a request to *read*; it is not consent to create folders in a
directory the user may have been curating for years, and `Projects/` is a common enough name
that theirs may already mean something else.

Decide with one check — does the vault contain notes this plugin did not put there?

```bash
# Any markdown outside the paths this plugin owns?
find "$DEVWB_VAULT" -name '*.md' -not -path '*/.git/*' \
  -not -path "$DEVWB_VAULT/Projects/*" \
  -not -path "$DEVWB_VAULT/Resources/*" \
  -not -path "$DEVWB_VAULT/Contributions/*" \
  -not -path "$DEVWB_VAULT/Archived/*" | head -5
```

- **Empty vault, or nothing but this plugin's own folders** → create the two files without asking.
  There is nothing to disturb, and prompting on an empty vault is noise.
- **Existing notes, or a `Projects/` folder this plugin did not create** → stop and ask once,
  naming exactly what you would create and where:

  > This vault has notes in it already. To track work per repo I'd create
  > `Projects/WorkspaceIndex.md` and `TasksArchive.md` at the vault root. Create them?

  If they decline, answer their question from what you can read and do not write anything. Do not
  re-ask in the same session.

The same applies in Step 2: scaffolding a **workspace** into an existing `Projects/` folder is a
first write to space the user may already be using. Name the folder you are about to create and
confirm, unless this plugin created `Projects/` itself.

Once either file exists, this step is done and never asks again.

## Step 1 — Locate the workspace

The vault holds an index that maps each repo to its workspace folder, by a path **relative to this machine's code root**:
`$DEVWB_VAULT/Projects/WorkspaceIndex.md`

**`WorkspaceIndex.md` is the only way to choose a workspace.** Never pick one by browsing `Projects/` or by
grepping for a term — a trial or archived copy can look more relevant than the live workspace,
because it is the one that has been reorganised. Read the index first, every time.

1. Determine the current repo's absolute path: `git rev-parse --show-toplevel` (fall back to the cwd
   if not a git repo). Call its basename `<repo>`.

   **Resolve the code root**, which is what index rows are relative to: the `CODE_ROOT` environment
   variable, then `${XDG_CONFIG_HOME:-~/.config}/dev-workbook/code-root` (or the pre-3.0 `…/claudesidion/code-root`), then the legacy
   `~/.claude/code-root` (one line each, whitespace trimmed, leading `~/` or `$HOME/` expanded),
   then the default `~/code`. `dev-workbook code-root` prints the result.

2. Read `WorkspaceIndex.md` and match. Rows hold paths **relative to the code root**; a row starting with
   `/` is absolute and matched literally. See "Paths are machine-relative" in
   [reference/templates.md](reference/templates.md).
   - **Path match** → use the workspace it names.
   - **No path match** → fall back to **basename**. On a single match, check whether that row's
     recorded path exists on this machine. If it does **not**, the repo moved: confirm and update
     the row. If it **does**, you are simply on a different machine — use the workspace and
     **change nothing**. Rewriting there is what makes rows ping-pong between machines.
   - **Several basename matches** → ask which. Do not guess.
   - **No match at all, and the index has rows** → **stop.** Every relative row missing at once
     means the code root is wrong or unset, not that this is a new repo. Say which root you
     resolved and where it came from, and do not scaffold — a second workspace for an existing repo
     is the split-brain this index exists to prevent.
   - **No match, and the index is empty** → genuinely new. Scaffold (Step 2) and add a row.
   - **`WorkspaceIndex.md` missing** → create it with the header from
     [reference/templates.md](reference/templates.md), then scaffold — subject to the Step 0
     consent gate if this is the first write to a vault that already has content.

3. **Check for a trial workspace.** `WorkspaceIndex.md` may carry a `## Trial workspaces` section listing a
   second, not-yet-adopted workspace for the same repo. If the repo you matched appears there:
   - The **main table's row is authoritative**. Write there, not to the trial.
   - Say so in one line — "note that `<trial>` also exists as a trial copy; writing to the live
     workspace" — so the user can redirect you if they meant the trial.
   - **Never write to both.** Two workspaces receiving the same entry is exactly the split-brain the
     trial section exists to prevent.

   Write to a trial workspace only when the user names it explicitly.

## Step 1b — Confirm the workspace is structured

A workspace is structured if it contains `.vault-config.json`. Every workspace this version creates
or writes to is structured; the flat layout was retired in 1.0.

If a workspace has **no** `.vault-config.json`, it predates 1.0 and this version cannot read or
write it. Say so plainly and stop:

> `Projects/<name>/` uses the flat layout, which this version no longer supports. Pin the plugin to
> `v0.4.x` and run `migrate-workspace` to convert it, then upgrade again.

Do not attempt to read it, do not offer to convert it, and above all do not scaffold a second
workspace alongside it.

The full contract — folders, frontmatter fields, legal `status` values, how to supersede a decision —
is in [reference/structure.md](reference/structure.md). **Read it before writing.**

## Step 2 — Scaffold a workspace (first use for a repo only)

**Workspaces are structured.** The flat layout was retired in 1.0 and is no longer created, read
or written.

To scaffold:

1. Create `$DEVWB_VAULT/Projects/<Repo>/` — the repo's name in PascalCase (`home-budgeter` →
   `HomeBudgeter`) — and, inside it, the folders from
   [reference/structure.md](reference/structure.md): `Tickets/`, `Epics/`, `Playbooks/`, `Research/`,
   `Notes/`, `Decisions/`, `Threads/`, `Log/`. **Create each on first use, never empty** — an empty folder is
   noise in the sidebar and tells the reader nothing.
2. Create `Overview.md` from the template in [reference/templates.md](reference/templates.md) — what
   the repo is, current focus, next up, the repo path relative to the code root, links to external
   trackers.
3. Create `ProgressLog.md` as a **one-line-per-day index**, not a stack of entries. The detail lives
   in `Log/<date>.md`.
4. Write `.vault-config.json` — this file is what marks the workspace structured; nothing else does.
   A new workspace has no content to derive topics from, so start with `"topics": {}` and add them as
   subjects emerge. The indexes work from day one; the TopicIndex is simply empty until there are
   topics.

```json
{
  "project": "<short-slug>",
  "generated_types": ["index", "log-index"],
  "index_types": ["index", "log-index", "overview", "meta", "glossary", "summary"],
  "min_hits": 3,
  "title_weight": 4,
  "topics": {}
}
```

The folder skeleton is **fixed by the contract**, not configured here — every workspace uses the same
folder names and the same document types, and skills may rely on that. What stays per-project is the
**vocabulary**: `topics`, `min_hits`, `title_weight`, and optionally `root_notes`.

5. Add the row to `WorkspaceIndex.md`. Record the repo's path **relative to the code root** (just `<repo>` for a repo sitting directly in it); use an absolute path only for a repo outside the root.

**Growing the topic vocabulary.** Add a topic once three or four notes would carry it — earlier and
it is noise, later and the index has a gap. Each topic needs specific patterns; one matching a common
English word tags half the workspace and makes the index useless. After editing `.vault-config.json`,
the next session-end hook run re-derives topics across every note.

## Step 3 — Read before you write

Before acting on a task or answering "what's the status", read the workspace's current state. This is
the context that would otherwise be lost.

- `Overview.md` (its `## Next up` is the queued work), `ThreadsIndex.md` (open threads and active
  playbooks with their counts), and the newest lines of `ProgressLog.md`, following the top one or
  two dates into `Log/<date>.md` for the detail.

## Answering "what's next" / status questions

First, check the question is the one this skill answers. "What's the status of this repo" usually
means **git** — branch, uncommitted changes, whether it is pushed. Answer that from git and stop.
This skill is for *where the work stands*: what to pick up next, what was decided, what is
unfinished. If it is ambiguous, the cheapest resolution is to answer the git question and offer the
other: "on `main`, clean, 2 commits ahead — want the work-in-progress picture from the vault too?"

For a genuine next-work question the vault is the source of truth — check it **before** any issue
tracker (`glab`/`gh`) or planning doc:

1. Locate the workspace (Step 1). If the repo has **no** workspace yet, say so and offer to bootstrap
   it with `ingest-project-docs` — do not silently fall back to the tracker.
2. Read `Overview.md` — its `## Next up` section is the direct answer, and "current focus" frames it.
   Then `ThreadsIndex.md` for open threads and active playbooks, following the top items into their
   notes. `TopicIndex.md` answers "what do we have on X" directly.
   - **Legacy workspace with no `## Next up`:** fall back to the `Next:` line of the newest
     `Log/<date>.md`, say it came from an old log, and offer to move it into the Overview.
3. Answer from that. Prioritize: `## Next up` first, then open threads and active playbooks.
4. Only consult the tracker as a *supplement* — to enrich an item or if the vault is genuinely silent —
   and mention that you're going beyond the vault when you do.

**Check the workspace is current before trusting it over a tracker.** That preference is earned by a
workspace someone has been keeping up; it is wrong for one that is empty or months behind, where
deferring to it means answering from stale information and calling it the source of truth. Compare
the newest `ProgressLog.md` date against the repo's last commit date:

- **Workspace within a few days of the last commit** → proceed as above; it is current.
- **Workspace materially behind the repo** (say a week or more of commits it does not mention) →
  say so in one line, answer from the vault *and* the recent commits together, and offer to log the
  gap: "the workspace was last updated 2026-08-12 and there are 23 commits since — here's what it
  has, plus what the commits show; want me to bring it up to date?"
- **Workspace exists but is effectively empty** (a scaffold with no logged work) → say so and answer
  from git and the tracker, rather than reporting that there is nothing to do.

## Step 4 — Write back (on trigger only)

This step runs only when one of the triggers in "When to log progress" below fires — an explicit
request, or the user closing out the session. It is not something to do as work happens.

Golden rule: **never overwrite existing content.** Read the file, then append or edit in place.
Create a file (with its header) only if it is absent.

### Write one note per fact

Read [reference/structure.md](reference/structure.md) first. In short:

- **The day's log** — write `Log/YYYY-MM-DD.md` (`type: log`, `date:` matching the filename) as
  **one** `Did` / `Decided` / `Learned` / `Links` block. If the day's note already exists, **merge
  into its sections** — never add a second block or a `###` sub-entry, and fix any earlier line the
  day's later work made wrong. **No `Next:` line.** Then add or update that day's one-line entry in
  the root `ProgressLog.md`, newest first. Never append a dated entry to the root `ProgressLog.md`
  itself — it is an index.
- **Next up** — rewrite `Overview.md`'s `## Next up`: remove what got done, add what is now next,
  at most five bullets, each linking its thread or playbook. This is the only place next work is
  written.
- **A decision** — a **new note** in `Decisions/`, named for the decision as a PascalCase claim, with
  `type: decision`, `status: active`, `decided: YYYY-MM-DD`, and `tickets:`. Never append to a
  `Decisions.md` — in this layout that file does not exist and must not be created.
- **Superseding a decision** — when the new decision replaces an old one, **edit the old note**: set
  `status: superseded`, add `superseded_by:`, and put a `> [!warning]` callout under its heading.
  Add the matching `supersedes:` and `> [!note]` callout on the new one. Skipping this is the single
  failure this layout exists to prevent — both notes then read as current.
- **A thread** — one note per thread in `Threads/`, `type: thread`. Tick `- [x]` inside it as items
  finish — the item text stays one line, with no "done on <date>" or outcome narrative appended.
  When nothing is left — or the user says the thread is done or abandoned — **close it**: move its
  decisions, durable knowledge and leftover items to their own notes, then reduce it to the closing
  stub (`status: done`, `closed:`, Goal / Outcome / Moved to). See "Closing a thread" in
  [reference/structure.md](reference/structure.md).
- **A playbook** — an ordered procedure goes in `Playbooks/` as `<Subject>Playbook.md`,
  `type: playbook`. While it is being executed it is the tracker: tick its steps in place and do
  not open a thread that repeats them.
- **Overview** — update "current focus" when the direction of the work shifts.
- **Time tracking** — only if `TimeTracking.md` exists: measure the sittings since `tracked_through:`
  and update the table, per [reference/time-tracking.md](reference/time-tracking.md).
- **Names** — every note is PascalCase: `FrameworkIsFastapiOverDjango`, `VaultPushReliability`,
  `AdminApiPermissionsAudit`, `ACME-1701-NaturalSortAdApprovals`; logs stay `YYYY-MM-DD`. The
  `# Heading` is the readable sentence-case form. Full table: "Naming notes" in
  [reference/structure.md](reference/structure.md).

### Current-state notes are rewritten, not appended

Every note except a log is **current state** — see "Two kinds of note" in
[reference/structure.md](reference/structure.md). When the work changes one, **rewrite it in place
so it is true today**: delete finished or wrong lines, do not annotate them ("~~X~~", "update:",
"now done"). Git holds the history. When you touch a current-state note that already breaks its
template, bring it into the template as part of the same edit.

**Removing something? Remove its references too.** When a decision is superseded, a thread closes
or a note is deleted or renamed, grep the workspace for links and mentions of it and fix every
current-state note that still points at it. Logs are history and keep their links.

Templates for every type, and the naming table, are in
[reference/templates.md](reference/templates.md) and [reference/structure.md](reference/structure.md).
- **Never create** `Decisions.md`, `Open Threads.md`, or a dated section inside the root
  `ProgressLog.md`. Those are retired flat-layout files; creating them produces two contradictory
  sources of truth in one workspace.

**Do not hand-write `project:`, `topics:` or `tags:`.** The `vault-maintain` SessionEnd hook derives
them and rewrites them anyway. Write `type`, `status`, the dates and the body; the hook fills in the
rest and regenerates `TopicIndex.md` and `TicketsIndex.md` before the vault is committed. Write
`topics:` explicitly only when you know the derived guess would be wrong — a hand-written list is
respected.

**Never hand-edit `TopicIndex.md` or `TicketsIndex.md`.** They are generated; edits are lost.

### How to write a wikilink

Every markdown viewer resolves `[[target]]` the same way: it names each note whose vault path ends
with `target`. One match is a link; two or more is ambiguous, and viewers disagree about what an
ambiguous link means — Obsidian silently picks one, often another project's, and Foam refuses to.
So the rule is: **write the shortest path that names exactly one note.**

- **A uniquely-named note → link it bare.** `[[UseTokenBucketOverFixedWindow]]`.
  This is the normal case in a structured workspace: one note per fact gives PascalCase names that
  are naturally unique. A bare link is readable and survives the workspace being renamed or moved.
- **A per-workspace structural file → always prefix it with the workspace**, even from inside that
  workspace. `[[Takeoffs/Overview]]`, `[[Takeoffs/ProgressLog]]`, `[[Takeoffs/DecisionsIndex]]`.
  These names — `Overview`, `ProgressLog`, `TopicIndex`, `TicketsIndex`, `ThreadsIndex`,
  `DecisionsIndex`, `TimeTracking` — exist once per workspace **by design**, so a bare link to one
  is ambiguous across the vault.
- **A log day → prefix it with the workspace's `Log/` path when the date is not unique**, and show
  the date: `[[Takeoffs/Log/2026-10-04|2026-10-04]]`. Several workspaces often log the same day.
  The `vault-maintain` lint reports a bare one as `ambiguous-link`.
- **Inside a table cell → never alias.** Write `[[Takeoffs/Log/2026-10-04]]`, not
  `[[…|2026-10-04]]`: the alias pipe splits the row into phantom columns in any viewer that ignores
  the `\|` escape. The lint reports one as `table-alias`.

There is **no same-folder exception.** A bare `[[Overview]]` in a workspace's own notes is still
ambiguous, and it is often written from a different folder (`ProgressLog.md` links into `Log/`), so
even Obsidian's same-folder preference does not apply.

**Never disambiguate by rewriting a bare link to a vault-wide search result.** A `[[Decisions]]`
looked up across the whole vault binds to whichever workspace matches first, and the result *resolves
cleanly* — so a link check calls it healthy while it silently points at another project's notes. That
is corrupted provenance, and it is harder to spot than a broken link. If a bare link is ambiguous,
resolve it against the file that contains it, not against the vault.

Cross-link between notes and to general `[[notes]]` (from the `capture-notes` skill) so the
workspace stays navigable in the vault's graph.

## When the vault contradicts these instructions

The vault is older than this skill and does not always match it. When they disagree, **say so in one
line and keep going** — do not silently pick one, and do not stop and interrogate the user over
something small.

- **Two workspaces claim the same repo** → write to the one in `WorkspaceIndex.md`'s main table; mention the
  trial exists. (Step 1.)
- **The superseded decision has no note** → record the replacement in prose, not frontmatter, and say
  you did. (See [reference/structure.md](reference/structure.md).)
- **An existing file breaks the format this skill documents** → if you are editing that note anyway,
  bring it into its template as part of the edit. Notes you are not touching are left for the
  `condense-vault` reconcile pass — do not sweep the workspace mid-task.
- **The workspace predates 2.0 names** (`Progress Log.md`, `Topic Index.md`, kebab-case or spaced
  note names) → read the old names, write new notes with the 2.0 names, and say once that the
  `condense-vault` reconcile pass will rename the rest. Do not rename on a logging pass.
- **A note carries frontmatter this contract does not list** → leave it, do not copy it forward.
- **The workspace is `status: paused` but the user is doing work in it** → log the work and ask
  whether to un-pause. Do not change project status on your own initiative.

Stop and ask only when writing would **destroy or contradict** something — never merely because the
vault is untidy.

## Maintaining the TasksArchive

`$DEVWB_VAULT/TasksArchive.md` is the quick-reference the user scans before a personal update
meeting: **one line per working day**, condensed enough to take in at a glance months later. It is
the thin layer above the per-repo `ProgressLog.md` files, never a replacement for them.

**Append today's row when the session is closed out**, alongside the ProgressLog entry — on the
same triggers as everything else in "When to log progress" below, never mid-session.

### Structure

Newest year first (`# 2026`), and within it newest month first (`## Aug 2026`). Each month has a
projects header above its table, then the table itself:

```markdown
## Aug 2026

### Month's Projects
[[portal.example.com/Overview|portal.example.com]], [[home-budgeter/Overview|home-budgeter]]

| Date | Tasks |
| ---- | ----- |
| 5    | ...   |
```

- **Exactly two columns** — `Date` and `Tasks`, nothing more. Never widen the table.
- **Date column** — the bare day number, nothing else. Days with no work get no row.
- **Month's Projects** — every project touched that month, most-active first. These are the only
  links that should point at a project `Overview`.
- **New month** → add a new `## <Mon YYYY>` section above the previous one, with its own projects
  header and table. Add the projects header entry the first time a project appears that month.

### Writing a row

Rows are **terse by design** — the archive is scanned, not read. One short clause per project touched
that day, **three to four words each**, comma-separated, at a very high level. The detail belongs in
that project's `ProgressLog`; do not restage it here.

- Name the project when the clause needs the context (`home-budgeter Phase 0 landed`), and carry a
  ticket number only where it *is* the shortest identifier (`ACME-1763 Laravel 13 planned`).
- Bold a genuine milestone — a release, an epic completing (`**ACME-1504 ready for review**`).
- Several projects in one day → one clause each, project named first so they stay separable.

**No links inside table cells.** A wikilink's alias pipe breaks the table row into phantom columns
in viewers that ignore the `\|` escape, and the links crowd out the few words the cell is meant to carry. Project
links belong in the `Month's Projects` line above the table, which is the one place they go.

Write it as a cell that renders in one line, e.g.:

```markdown
| 19 | ACME-1656 billing joins landed, home-budgeter deployed |
| 12 | **ACME-1763 done — Laravel 10→13 climb complete** |
```

### Which day a session books under

Book work under the date it **started**. A session that runs past midnight still belongs to the day
it began, so it appends to that day's row rather than opening a new one. If a row for the day already
exists, extend it — never add a second row for the same date.

## Time tracking (optional)

Some projects track hours per phase against their estimates. It is **opt-in per workspace**: set it
up only when the user asks ("set up time tracking", "track my hours on this project"). Never create
`TimeTracking.md` unprompted, and never suggest it as part of an ordinary logging pass.

To set it up: create `TimeTracking.md` from the template in
[reference/templates.md](reference/templates.md), with one row per phase (and subphase, where the
plan estimates one) taken from the project's playbooks. Then measure the time already spent, as far
back as the transcripts go, with the method in
[reference/time-tracking.md](reference/time-tracking.md). Tell the user how far back that reached:
transcripts expire after 30 days by default, so anything earlier can only come from the user's own records.

Once the file exists, every close-out updates it (see "When to log progress").

## When to log progress

Progress logging is **not** continuous. Do not append ProgressLog entries, Decisions, thread
updates, or TasksArchive rows mid-session as work happens — that noise interrupts the actual coding
work. Write to the vault only on one of these two triggers:

- **The user explicitly asks** — "log progress", "record what we did", "record this decision",
  "update the vault", "note this down".
- **The user says to close out the session** — "close out the session", "wrap up", "we're done for
  the day", "end of session", or an equivalent.

When one of those fires, do the whole write in one pass: write or merge the day's log and its
ProgressLog line, rewrite `## Next up`, update threads (closing any that finished), playbooks and
decisions as needed, update `TimeTracking.md` if the workspace has one, and append the day's row to [[TasksArchive]] (see "Maintaining the TasksArchive" above).

Reading the vault is unrestricted — read it freely whenever you need context (Step 3, and the
"what's next" flow). The restriction is on *writes*.

Keep each write incremental — the golden rule above ("never overwrite; append or edit in place")
governs *how*.

## Keep vault I/O out of the transcript

Vault notes are long prose. Echoing their full text into the transcript buries the actual coding work
the user is trying to follow, so **never dump a vault file's contents into the conversation** — not
even when the user has the agent running verbose.

- **Reading** — prefer targeted Bash extraction over reading whole files: `grep`, `sed -n '1,40p'`,
  or an `awk` range that pulls just the section you need (the latest `## YYYY-MM-DD` entry, the
  unchecked `- [ ]` lines, the "current focus" paragraph). Read a whole file only when you genuinely
  need all of it.
- **Writing** — append and edit with Bash (`cat >> … <<'EOF'`, `sed -i''`, a small `python3` script)
  and send any command output to `/dev/null`. A successful write needs no output at all.
- **Reporting** — after writing, say what you did in one short line ("logged today's progress and the
  archive row"), not by quoting or re-printing what was written. Never print a diff of the note.
- **Verification** — if you must confirm a write landed, check cheaply (`tail -n 3`, a `grep -c`), not
  by re-reading the file into context.

## Vault writing style

Write for **someone scanning for one fact**, not someone reading start to finish. The full rules and per-type length budgets are in "Writing style" in [reference/structure.md](reference/structure.md); in short:

- **Answer first.** The first line under any heading is the answer; setup comes after, if at all.
- **Bullets and `**Key:** value` pairs over paragraphs** — a paragraph is at most three short sentences.
- **Outcome, not process.** What is true or was decided, never the story of getting there.
- **One fact, one place.** Link the specific note that owns a fact instead of restating it.
- **No stale pointers.** Remove references to finished, superseded or deleted things from current-state notes.
- **One continuous line per block** — no hard line breaks inside a paragraph, bullet or blockquote.

## Vault git sync

**Check who syncs first.** The plugin's hooks sync the vault at the session boundaries — on session start one pulls it to latest, and on session end one regenerates the indexes, then commits and pushes everything as a single commit. Each start writes a heartbeat to `.git/dev-workbook-hooks` inside the vault:

```bash
find "$(git -C "$DEVWB_VAULT" rev-parse --absolute-git-dir)" -maxdepth 1 -name dev-workbook-hooks -mmin -1440
```

- **Heartbeat less than a day old** → the hooks are installed. **Do not run `git pull`, `git add`, `git commit` or `git push` on the vault**; write the files and move on.
- **No heartbeat, or an old one** → this harness runs no hooks, so sync yourself: `git -C "$DEVWB_VAULT" pull --ff-only` before your first read, and when the user closes out the session run `dev-workbook maintain`, then stage only the paths the plugin owns (`git -C "$DEVWB_VAULT" add -- Projects Resources Contributions Home.md TasksArchive.md WorkPlanning.md`, skipping any that do not exist), commit them as one single-line commit (`vault: session updates YYYY-MM-DD`) and push. Never `git add -A`, and never commit mid-merge or on a detached HEAD. If the push fails, leave the commit and tell the user.

**Background sessions** (`CLAUDE_JOB_DIR` is set) never write a vault path directly — Claude Code blocks `Write`/`Edit` on the vault's checkout there, and a Bash write would sidestep the protection that block exists for. For each note you would create or change, run `dev-workbook stage "<vault-relative path>"` and do all reading and writing for that note at the path it prints: an existing note is copied there, a new one does not exist yet. Stage each note once. When the session ends, the hooks merge the staged notes into the vault three ways, so edits made there meanwhile survive; a conflicting edit stays staged and the next session reports it. `dev-workbook staged` lists what is waiting. Skip renames and deletions in a background session — leave them for an interactive one.

If the vault is not under version control, there is nothing to sync (and you should never `git init` it).
## Conventions

- Dates: `YYYY-MM-DD`. Tags (if used in frontmatter): lowercase, hyphenated.
- The vault links *out* to Jira/GitHub/GitLab; it does not push changes back to them.

## Templates

The index-note format and a template for every note type are in
[reference/templates.md](reference/templates.md).

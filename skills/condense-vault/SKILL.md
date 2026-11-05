---
name: condense-vault
description: Weekly cleanup routine for the user's markdown vault (Obsidian, Foam, …) — reconciles project workspaces against their note formats (strips stale "Next" pointers, dead references and stacked log entries, renames off-pattern notes, trims over-length notes, whatever their age), condenses stale content (untouched >3 months) down to bullet points everywhere, and outside project workspaces also deletes records of finished work older than that. Use when the user says "condense the vault", "clean up the vault", "run the vault cleanup", or when a SessionStart reminder from this plugin says the weekly condense run is due.
---

# Condensing the vault

Keep the vault lean and **true**. Two passes, one run:

1. **Reconcile** (Step 1) — every run, **regardless of age**: bring project workspaces back into their note formats, and every note in the vault onto PascalCase names. This is what removes stale "next work" pointers, references to superseded or deleted notes, and session-diary logs while they are still fresh enough to mislead.
2. **Condense and delete** (Steps 2–5) — age-gated: old content earns its place only in condensed form, and outside the project workspaces records of finished work eventually go away entirely. Project workspaces are condensed but never deleted from — they are the durable record.

This is a routine, not a per-note judgement call — run it over the whole vault in one pass.

**Vault location:** resolve in this order — (1) the `DEVWB_VAULT` environment variable (or the pre-3.0 `OBSIDIAN_VAULT`), (2) the config file `${XDG_CONFIG_HOME:-~/.config}/dev-workbook/vault` (or the pre-3.0 `…/claudesidion/vault`), (3) the legacy config file `~/.claude/obsidian-vault`, (4) the default `~/ObsidianVault`. A config file holds one line, the vault's path (whitespace trimmed, a leading `~/` or `$HOME/` expanded); `dev-workbook vault-path` prints the result. If none of them yields an existing directory, ask the user where their vault is and write the answer to `~/.config/dev-workbook/vault` (creating the folder) so every future session and hook finds it. Use the resolved absolute path (written below as `$DEVWB_VAULT`) for every read/write.

**Plugin tools** run through the `dev-workbook` command. If `command -v dev-workbook` finds nothing, run `python3 "<plugin root>/bin/dev-workbook"` instead — the plugin root is two levels above this skill's base directory. A skill installed on its own, outside the plugin, needs the command on PATH: `ln -s <plugin root>/bin/dev-workbook ~/.local/bin/`.

**Not in a background session.** If `CLAUDE_JOB_DIR` is set, stop and say the condense run needs an interactive session: it renames and deletes notes, which a background session cannot do safely.

## Step 1 — Reconcile formats and names (every run, any age)

The format rules are in [manage-project-workspaces/reference/structure.md](../manage-project-workspaces/reference/structure.md) — read "Two kinds of note", "Naming notes" and "Writing style" first, and use [templates.md](../manage-project-workspaces/reference/templates.md) for the target shape of each type.

**Start from a clean tree.** In a versioned vault, commit or stash any uncommitted changes before editing anything (see Step 5 for why), so this run's edits land in their own commit.

**Rename first.** Work through `legacy-name` and `bad-name` before anything else: every other fix writes links, and they should point at the final names.

**Every rename and move goes through the plugin's rename script** (`dev-workbook rename`) — never `git mv` or `mv` by hand. It moves the note (with `git mv` in a versioned vault) and rewrites every `[[link]]` and `supersedes:`/`superseded_by:` value that points at it, vault-wide, under a lock:

```bash
dev-workbook rename "<old vault-relative path>" "<new vault-relative path>"
```

Add `--dry-run` to see how many links a rename would rewrite. A link whose target also names another note is rewritten only inside the renamed note's own workspace, so links that meant the other note are left alone. Rewritten links use the shortest path that names only the moved note.

**Get the findings from the lint**, which ships with the plugin:

```bash
dev-workbook lint
```

Each line is `<workspace>/<path>: <code> — <detail>`. Work through them by code:

| Code | Fix |
| --- | --- |
| `log-next` | For each `Next:` line, check whether the step is done (later logs, threads, git). **Still open** → make sure it is in `Overview.md`'s `## Next up` or an open thread, adding it if not. Then **delete the line** from the log. |
| `log-stacked` | Merge the day's blocks into one `Did` / `Decided` / `Learned` / `Links` block. Where an earlier entry was overtaken later that day ("1.3 not yet done" … "1.3 done"), keep only the final state. |
| `over-budget` | Rewrite the note to its template: cut process narrative, dates on ticked items, commit SHAs and restated context; link out to the note that owns a fact. If it still will not fit, it is two notes — split it. |
| `stale-link` | A current-state note links a superseded decision or a finished thread. Repoint to the successor (`superseded_by`), or delete the line if it only existed to point at finished work. |
| `broken-link` | Find where the target went (`git log --diff-filter=DR --name-status -- '*<name>*'`). Renamed → repoint. Deleted → remove the link, keeping the plain text only if the sentence still needs it. |
| `ambiguous-link` | A bare log date or structural-file link (`[[2026-10-01]]`, `[[Overview]]`) that names a note in several workspaces. Run `dev-workbook qualify` once (add `--dry-run` first to see the count): it rewrites each to the copy in the linking note's own workspace, keeping the displayed text (`[[Alpha/Log/2026-10-01\|2026-10-01]]`). Fix any link it reports as unresolved by hand. |
| `index-link` | Replace the link to an index with a link to the specific note it meant. |
| `bad-name` | Rename to PascalCase per the naming table with the rename script, keeping the `# Heading` as the readable form; it rewrites the links. A **workspace folder** rename also updates its `WorkspaceIndex` row, its `Contributions/` note name and every `[[OldFolder/` link prefix (the TasksArchive's project lines included). |
| `dup-name` | Two notes share a name vault-wide. If the other copy is under `Archived/`, `git rm` the archived copy — Archived is expendable, and it is the one making links ambiguous. Otherwise rename the less-linked note to something more specific, as for `bad-name`. |
| `root-stray` | A plan, roadmap or guide → move into `Playbooks/` or `Research/` with the rename script, then set the right `type:`. A `Home.md` or other duplicate of `Overview.md` → merge anything unique into the Overview, then `git rm` it. A CV summary → `Contributions/` (merge into the project's existing summary if there is one). |
| `legacy-name` | A pre-2.0 name. A generated index (`Topic Index.md` and the like) → `git rm` it; the hook regenerates it under its new name. Anything else → rename as for `bad-name`. |
| `unclosed-thread` | Close the thread as in "Closing a thread" in [structure.md](../manage-project-workspaces/reference/structure.md): move decisions, durable knowledge and leftover items to their own notes, then reduce it to the closing stub. Leftover items that fit nowhere go in the report for the user to decide on — never drop them silently. |
| `missing-section` | Add the section the template requires: `## Next up` in an Overview (seed it from open threads and the newest log), `## TL;DR` in research, the playbook headings in a playbook. |
| `hard-wrap` | Join the wrapped lines into one line per block. |
| `stacked-keys` | Turn the run of `**Key:** value` lines into list items (`- **Key:** value`), or put a blank line between them. Without one, CommonMark viewers join them into a single paragraph. |
| `table-alias` | Rewrite each `[[Target\|text]]` in a table cell as plain `[[Target]]`. An alias pipe splits the row in viewers that ignore the escape; if the cell then reads badly, move the link out of the table. |

Rules for this pass:

- **Logs are history.** Strip `Next:` lines and merge stacked blocks, but never rewrite what a log says happened.
- **Current-state notes are rewritten in place** — delete finished or wrong lines rather than annotating them.
- **A merge-then-remove is a move, not a deletion.** Removing a `root-stray` after its content has landed in another note is allowed inside `Projects/`; removing content is not.
- **Supersession needs evidence.** Do not mark a decision superseded or a thread done on a guess — leave the finding and list it in the report.
- **Re-run the lint at the end.** Report what is left and why.

## Step 2 — Find stale content

**Stale = last modified more than 3 months ago.** When the vault is versioned, use the last commit
date per file (`git -C "$DEVWB_VAULT" log -1 --format=%ad --date=short -- "<file>"`); otherwise
use filesystem mtime. A fast way to list candidates in a versioned vault:

```bash
cd "$DEVWB_VAULT" && cutoff=$(date -v-3m +%Y-%m-%d 2>/dev/null || date -d '-3 months' +%Y-%m-%d) \
  && git -c core.quotepath=off ls-files '*.md' | while IFS= read -r f; do
  d=$(git log -1 --format=%ad --date=short -- "$f")
  [ "$(printf '%s\n%s\n' "$d" "$cutoff" | sort | head -n1)" = "$d" ] && [ "$d" != "$cutoff" ] \
    && printf '%s\t%s\n' "$d" "$f"
done
```

Two portability notes baked into that snippet: string `<` comparison inside `[ ]` is bash-only (it breaks under zsh — compare via `sort` instead), and `core.quotepath=off` is required or filenames with non-ASCII characters (em-dashes, arrows) come out quoted and their dates come back empty.

Scan `Notes/`, `Resources/`, `Inbox/`, `Archived/`, `Projects/`, and loose root notes. Never touch a dot-directory (`.obsidian/`, `.vscode/`, `.foam/`, `.git/`, …), attachments, or non-markdown files — dot-directories hold viewer settings and templates, not notes.

**Never condense or delete anything under `Contributions/`.** Those are living career summaries
maintained by `summarize-contribution` — one per project, updated in place over a project's whole
life. Staleness there is expected and meaningful: a project that ended two years ago has a summary
nobody has touched since, and that is the finished document, not neglect. Condensing one would
destroy the prose it exists to hold.

## Step 3 — Sort each stale file into one of three buckets

1. **Delete** — records of work that is finished: notes about a PR/MR that merged, unfiled captures
   that were never worth filing, retired material in `Archived/`. Signals: frontmatter
   `status: done|closed|merged|complete|shipped`, a title or body naming a ticket/PR explicitly
   marked merged or complete, every checkbox checked with no forward-looking content.
   When the note names a ticket/PR but its state is not recorded in the note,
   you may check the tracker (`gh`/`glab`/Jira link) read-only; if the state still can't be
   established, condense instead of deleting.

   **This bucket applies outside project workspaces only** — `Resources/`, `Inbox/`, `Archived/`,
   and loose root notes. Inside `Projects/<repo>/`, nothing is deleted: a workspace note is the
   durable record of why work happened, and `shipped` is the *normal terminal status* of a ticket
   note rather than a signal that it is disposable. Condense stale workspace notes; never remove
   them. See "Project workspaces are never deleted from" below.
2. **Condense** — everything else that is stale: reduce verbose prose to terse bullet points.
3. **Leave alone** — stale files that are already terse (roughly: mostly bullets already, or under
   ~15 lines of body), and anything that is a living index (`WorkspaceIndex.md`, `MEMORY`-style indexes,
   `Overview.md` files).

If genuinely unsure between delete and condense, condense — the next run can delete it once the
signal is clearer.

### Project workspaces are never deleted from

Anything under `Projects/<repo>/` is condensed, never deleted. The delete bucket is for material
that records *that something happened*; a workspace note records *why it happened and what it
touched*, which stays useful long after the work ships and often after the tracker is gone.

This is a rule about **location**, not about layout — it holds whether or not the workspace has a
`.vault-config.json` (see
[manage-project-workspaces/reference/structure.md](../manage-project-workspaces/reference/structure.md)).
The specifics that matter most:

- **Never delete a note with `type: ticket`, whatever its status.** In the structured layout
  `shipped` is what a ticket note *becomes* when the work lands — it is the terminal state of a
  healthy note, not a marker of one that has outlived its use. The note exists precisely to outlive
  the ticket: it holds why the work was done and what it touched, long after the tracker issue is
  closed and often after the tracker itself is gone. `TicketsIndex.md` is regenerated from these
  notes, so deleting them also silently rewrites the index. Condense a stale shipped ticket; never
  remove it.
- **Never delete a note with `type: decision` or `type: convention`**, whatever its status. A
  `status: superseded` decision is not finished work — it is the record of what was true before, and
  the thing that stops a stale claim being read as current. Condense it if it is stale; never remove
  it.
- **Never delete or condense a generated index** — `TopicIndex.md`, `TicketsIndex.md`,
  `DecisionsIndex.md`, `ThreadsIndex.md`, or the root `ProgressLog.md`. They are
  rebuilt from the notes and carry no original content. Condensing one just gets overwritten;
  deleting one loses nothing but produces confusing churn.
- **Never delete `.vault-config.json`.** It is the only thing marking a workspace as a workspace;
  without it every skill treats the folder as an unsupported pre-1.0 layout.
- `Log/<date>.md` notes are ordinary content: condense old ones, but deleting a day's log deletes
  the only record of that day.

The one removal allowed inside a workspace is **merge-then-remove** in Step 1: a stray root file (a `Home.md` duplicating the Overview, say) may be removed once everything it held has landed in another note. That moves content; it does not delete it.

`status: reference` means "durable material, no lifecycle" — it is never a delete signal.

### Where the delete bucket does apply

Outside `Projects/`, in rough order of how much accumulates there:

- **`Archived/`** — retired workspaces and superseded material, expendable by design. The session
  hooks deliberately neither commit nor report changes here, so it is the one area that grows
  without any upkeep. It *is* tracked in git, so deletions stay recoverable.
- **`Inbox/`** — unfiled captures. Anything still here after three months was never worth filing.
- **`Resources/`** — reference material. Delete only what is genuinely spent: a link that 404s, a
  workaround for a bug since fixed, a note for a tool no longer used. Most of this condenses.
- **Loose root notes** other than the ones the plugin maintains.

**Never delete** `Home.md`, `TasksArchive.md`, `WorkPlanning.md`, anything under
`Contributions/`, or any dot-directory (`.obsidian/`, `.vscode/`, `.foam/`, …).

## Step 4 — Condense

Rewrite the note body as bullet points, keeping:

- the YAML frontmatter (update nothing in it except adding `condensed: YYYY-MM-DD`),
- the title heading,
- every `[[wikilink]]` and external URL that carries information (fold them into the bullets),
- the facts — names, numbers, decisions, conclusions.

Drop: narrative prose, restated context, hedging, worked examples, anything recoverable from a
linked source. A good condensed note is the bullet list you'd want when the topic resurfaces in a
year. Target well under half the original length; a long note may become five bullets.

**Project workspaces** (`Projects/<repo>/`) condense each stale note **to its type's template** (see [templates.md](../manage-project-workspaces/reference/templates.md)) rather than to free bullets:
- `Log/<date>.md` — one `Did` / `Decided` / `Learned` / `Links` block; `Did` down to the outcomes that still matter.
- Decisions — keep every one; condense `Why` and `Rejected` to a line each.
- Threads — collapse `## Done` to one line per item; a `status: done` thread keeps only its goal and done list.
- Playbooks and research — `status: done` playbooks keep goal, done-when and the step titles; research keeps its TL;DR and the sections that still hold facts.

Rewrites also apply the vault writing style: **one continuous line per block** (unwrap any hard-wrapped prose you touch) and **scan-first prose** — the answer first, bullets over paragraphs, outcome not process. Condensed bullets are readable clauses, not telegraphic fragments.

## Step 5 — Delete

**Deletion requires a recycle bin. Check for one before deleting anything.**

The safety of this whole routine rests on one claim: a wrongly deleted note is recoverable from
the vault's git history. That claim is only true when the vault is a git repository with the
deletions committed. It is **false** for a vault that is not versioned, and this skill explicitly
supports those (Step 2 falls back to file mtimes for exactly that case).

So, before deleting:

```bash
git -C "$DEVWB_VAULT" rev-parse --is-inside-work-tree >/dev/null 2>&1 && echo versioned || echo unversioned
```

- **Versioned** → proceed. Deletions go in as a dedicated commit (Step 6), so `git revert` or
  `git checkout <sha>^ -- <path>` brings any note back.
- **Unversioned** → **do not delete anything.** Condense the bucket-1 files instead — down to a
  single line each if they are truly finished — and tell the user plainly: *"this vault is not
  under version control, so I condensed rather than deleted; deleting would be unrecoverable."*
  Offer `git init` as the fix. A cloud-synced vault (Drive, iCloud, Dropbox) does **not** count:
  per-file revision history is not the same as a commit you can revert, and it will not restore a
  file the sync has already propagated as deleted.

Also require a **clean working tree** before a versioned run. If the vault has uncommitted changes,
commit or stash them first — otherwise the "recoverable deletion commit" arrives mixed with the
user's unrelated in-progress edits, and recovering one deleted note means untangling it from work
that has nothing to do with this run.

Then delete the bucket-1 files outright with `git rm`. After deleting, grep the vault for
`[[wikilinks]]` to the deleted notes and remove or unlink those references so no dangling links
remain (a mention in a condensed summary line is fine as plain text).

## Step 6 — Stamp, commit, report

1. Write the run date (`YYYY-MM-DD`) to `$DEVWB_VAULT/.condense-last-run` (plain text, one line).
   The plugin's SessionStart reminder reads this to know when the next weekly run is due.
2. If versioned, commit and push everything as one commit. This is the one skill that commits its
   own work: the run deletes files in bulk, and a dedicated commit keeps that recoverable instead
   of folding it into the generic session commit the `SessionEnd` hook makes.

```bash
git -C "$DEVWB_VAULT" add -A \
  && git -C "$DEVWB_VAULT" commit -m "condense vault: <R> reconciled, <N> condensed, <M> deleted" \
  && git -C "$DEVWB_VAULT" push
```

   The message is a **single line with no body and no attribution** — no `Co-Authored-By`, no
   `Generated with` trailer. Pass exactly one `-m` flag and never a heredoc. Commit on the current
   branch; do **not** create branches. If `push` fails (no remote, offline, auth), leave the commit
   in place and tell the user; do not retry in a loop.

3. Report to the user: findings reconciled (counts per lint code, plus what is left), files deleted
   (with one-line reasons), files condensed (with rough size before → after), and anything skipped
   as unclear.

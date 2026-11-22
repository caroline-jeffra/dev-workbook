# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**What a breaking change means here.** This plugin's public surface is not an API — it is the
**layout it writes into your vault** and the **behaviour of the hooks**. A major version bump means
one of: a change to the workspace folder structure or note format that existing vaults would need
migrating for; a change to which paths the session-end hook commits; or a skill trigger changing so
that a phrase that used to invoke it no longer does. New skills, new hooks and additive frontmatter
are minor.

## [Unreleased]

## [3.7.0] — 2026-11-22

### Changed

- **Shorter skill descriptions.** Every skill's `description:` sits in context in every session, so the five now say what the skill is in one clause, keep one or two phrases per intent and every exclusion between skills, and drop the prose about what the skill writes. Description bytes, 3.6.0 to 3.7.0: `capture-notes` 376 to 205, `condense-vault` 624 to 332, `ingest-project-docs` 512 to 292, `manage-project-workspaces` 813 to 531, `summarize-contribution` 931 to 550, total 3,256 to 1,910 (about 41% smaller).
- **Dropped near-synonym triggers.** Gone: "track open threads", "update my contribution summary", "what should I put on my CV for this", "what did I accomplish on this project", "what were we doing on this", "record what we did", "pull in the docs/issues", "import existing context", "LinkedIn" and "going on pause". "what's the next task" is now "what's next". Every exclusion between skills is kept. This is a minor release: the dropped phrases are near-synonyms of kept ones, and descriptions route by meaning, so the same requests still reach the same skill.
- **Descriptions name no markdown viewer.** The vault is platform agnostic, so "(Obsidian, Foam, …)" is gone from every description and "save this to my vault/Obsidian" is now "save this to my vault". This reverses the 2.3.0 rule that kept "Obsidian" in descriptions for its trigger phrases.
- **New ticket trigger.** `manage-project-workspaces` also answers "status of <ticket>", matching the ticket-scoped reads added in 3.6.0.

### Added

- **`tests/test-skill-descriptions.py`** checks that each `SKILL.md` has one `name:` and one single-line `description:`, that an unquoted description has no `: `, no ` #` and no leading YAML indicator, that the pinned triggers and exclusions are still present, that no description names a markdown viewer, and that the descriptions stay within 600 bytes each and 2,000 together. Its `--self-test` deletes each pinned phrase from a temporary copy and requires the checks to fail. It applies the plain-scalar rules rather than parsing YAML, so it needs no dependency.

This release makes no claim about the blank `ingest-project-docs` entry in the skill listing, which looks like a budget shared by every installed skill rather than a per-skill cap.

## [3.6.0] — 2026-11-22

### Changed

- **`manage-project-workspaces` is a router plus reference files.** `SKILL.md` shrinks from 32,436 to 8,659 bytes and every request loads it; the rest moved to `reference/read.md` (what's next, status), `reference/closeout.md` (every write), `reference/scaffold.md` (vault-level files, new workspaces and the index matching rules that used to sit in `templates.md`) and `reference/time-tracking.md` (now also holds the setup text). The naming, wikilink and writing-style copies that `SKILL.md` carried are merged into `reference/structure.md`, its single home. `templates.md` is now an index of one file per note type under `reference/templates/`, each split verbatim. The match table, trial rule, `index_notes` and Step 1b text are unchanged, and no rule was dropped: `tests/skill-rules.tsv` pins every rule of 3.5.0 to exactly one file.
- **Bytes loaded per request, 3.5.0 to 3.6.0.** Read path (router plus `read.md`): 32,436 to 12,746. Ticket-scoped read (the same plus a ticket's Goal, Status and Next lines, about 440 bytes): 32,436 to about 13,200. Close-out path (router, `closeout.md`, the eight `structure.md` sections it names, the overview, progress-log, log, tasks-archive and decision templates, and the case-study prompts): 72,292 to 50,029. Worst case, every file in the skill: 80,552 to 84,679, because the index files and pointers are new.
- **Next work is stated at two levels (additive format change).** A ticket note carries a `**Next:**` line under `**Status:**`, and a "what's next" or "what's the status of ACME-1234" question is answered from the note's Goal, Status and Next lines alone. A note with no `**Next:**` yet falls back to that ticket's bullet in the Overview, a bare ticket number is confirmed against the full key before a note is used, and every vault path and key is quoted in the commands the skill runs. The Overview's `## Next up` is now a list of pointers with no cap (`KEY — [[ticket note]]` plus at most a 2–3 word state, or a thread or playbook for non-ticket work) instead of at most five task bullets. Existing Overviews convert on their next close-out: the task text moves into each ticket's `**Next:**`. `condense-vault` sends a still-open `log-next` step to the ticket's `**Next:**` when it belongs to a ticket, and the `log-next` lint message now says the step belongs in the ticket note or the Overview.

### Added

- **`tests/test-skill-rules.sh`** pins every rule to one home, keeps the router body under 8,192 bytes, checks the frozen router text against `v3.5.0`, checks the per-type templates against the 3.5.0 sections, checks every relative link and named section under `skills/`, and mutation-tests itself.

## [3.5.0] — 2026-11-22

### Added

- **`dev-workbook context`.** One read-only command that prints, on a single `key=value` line, what every skill used to work out from prose: the vault and code root and which config tier supplied each (`vault_from`, `code_root_from`), the repo's workspace match (`path`, `basename`, `moved`, `ambiguous`, `unmatched`, `misconfigured`, `new`, `no-index`, `no-vault`), whether the workspace is structured, a trial workspace, whether to ask before writing to the vault, who syncs it (`hooks`, `self`, `none`) and whether this is a background session. Values with spaces or quotes are JSON-quoted, and a failure still prints every key plus `error=`. Index rows it cannot read, or a workspace name with anything beyond letters, digits, dots, dashes, underscores and spaces, are never matched, so they lead to a question rather than a scaffold or a shell command.

### Changed

- **The skills read it instead of repeating the rules.** `manage-project-workspaces`, `capture-notes`, `ingest-project-docs`, `summarize-contribution` and `condense-vault` start from `dev-workbook context` and keep a short prose fallback for standalone installs. When `DEVWB_VAULT` names a missing folder they say so and stop, instead of writing a config file the variable would override. `manage-project-workspaces` is about 3 KB smaller.
- **A repo with no row in a populated index now asks before scaffolding** (`match=unmatched`). The skill used to say stop and the templates reference said scaffold; both now say ask first, and scaffold only on a yes. When no indexed path exists on this machine the code root is wrong, and the skill still stops (`match=misconfigured`), now even when the repo's name matches a row.

## [3.4.0] — 2026-11-15

### Added

- **Optional graphify support.** When a repo has a graphify graph (`graphify-out/graph.json`), `ingest-project-docs` seeds a `Research/ArchitectureMap.md` from its areas, `manage-project-workspaces` answers structural questions with `graphify query` before a text search, and `summarize-contribution` maps the files you modified onto the graph's areas as evidence of breadth. Each checks the graph's `built_at_commit` against `HEAD` and says when it is stale, and each skips vendored communities. No skill builds or updates a graph; `ingest-project-docs` offers `/graphify` once for a newly ingested repo when the CLI is installed. Graph output never goes into the vault.
- **A `Diagrams/` folder** (`type: diagram`) for one diagram per note, named `<Area><Subject>`. By default a diagram is a Mermaid note; when the vault has the Excalidraw plugin and you want a drawing to edit by hand, it is an `.excalidraw.md` drawing, embedded with `![[Name.excalidraw]]`. Skills read a drawing through its `## Text Elements`, and never rewrite one you have edited.
- Detection, formats and rules for both live in one place: `skills/manage-project-workspaces/reference/integrations.md`.

### Hooks

- The session-end maintainer recognises Excalidraw drawings and leaves their frontmatter and body untouched. The lint checks only a drawing's name and that it sits in `Diagrams/`, and an embed of a drawing (`![[Name.excalidraw]]`) is now checked like any other link.

## [3.3.0] — 2026-11-15

### Changed

- **Note names are built to be skimmed.** Within a workspace, names used to carry the project's name (`OrchardStatusFlowMap`), every ticket began with the same key (`ACME-2378-…`), and every playbook ended in `Playbook`, so a sorted or truncated file list showed the same characters over and over. The naming contract now says a name never repeats what its folder already says, and spends its first characters on what tells notes apart: **area first, kind last** (`<Area><Subject><Kind>`). Decisions lead with their subject rather than a verb, threads and notes end in a short fixed vocabulary when they need a kind, and anything but a decision is two to four words.
- **Tickets are `<number>-<Subject>`** (`2378-AcfRestApiHardening`). The key stays in `tickets:` and the heading, and `TicketsIndex.md` now takes a ticket note's key from `tickets:`.
- **Playbooks drop the `Playbook` suffix** (`RelaySetup`).
- **Names need only be unique within their workspace.** Two workspaces may share a name; links to it carry the workspace path (`[[Orchard/CompletedItems]]`). General notes outside `Projects/` stay unique across the vault.

### Lint

- `bad-name` now reports a name that starts with its workspace's name, a keyed ticket name, and a playbook ending in `Playbook` — each with the fix. `condense-vault`'s reconcile pass renames them with the rename script, which rewrites every link.
- `dup-name` no longer reports the same name in two workspaces; it still reports a clash inside one workspace or with a note outside every workspace.
- `ambiguous-link` now also reports a bare link to a name that more than one workspace uses. `dev-workbook qualify` fixes it as before.

Existing names keep working; the lint flags them for the next condense run.

## [3.2.0] — 2026-11-15

### Added

- **Case-study flagging.** Reviews and interviews ask for specific examples — an incident, a disagreement, a mistake you owned — and the best ones rarely show up in commits. A new prompt list, `Contributions/CaseStudyPrompts.md`, holds the questions with a stable slug each, whether to collect a success *and* a failure (`pair`), and how visible such a story is in git. `summarize-contribution` seeds it on first run from 21 common prompts, and the vault copy is yours to edit.
- **`manage-project-workspaces` flags candidates as work is logged.** At close-out it checks the session against the prompts and adds a ``- **Case study:** … — `slug` `slug` · outcome`` line to the day's log for each real match, tagging every prompt the story answers and watching hardest for the ones git cannot show: disagreements, scope pushback, mistakes caught, abandoned approaches, people unblocked.
- **`summarize-contribution` writes a `## Case studies` section.** It harvests the log flags, matches major efforts, decision notes, git signals and tracker evidence against the prompts, and writes each story in STAR shape (plus a reflection for failures), tagged with its prompts, outcome and `ready`/`candidate` grade. A Coverage line names the prompts with no story and the `pair` prompts missing a success or a failure. A new `case_studies:` frontmatter field lists the covered slugs so one prompt can be searched across every project.
- **Case-study signals in `reference/git-evidence.md`** — reverts of your own commits, off-hours fixes, commit bursts, AI co-author trailers, first touches of each directory, closed-unmerged PRs, the most-discussed PRs and PRs you reviewed. Step 5 now asks for review threads, ticket comments and design docs explicitly.

### Changed

- `condense-vault` keeps every `Case study:` line word for word when it condenses or merges a log.

## [3.1.0] — 2026-11-05

### Added

- **Background sessions can write the vault again, without clobbering anything.** Claude Code blocks `Write`/`Edit` on a git checkout from a background session until it isolates itself in a worktree, and the vault is a git checkout, so a background session's notes were never written. The guard stays on. Instead the skills stage each note with the new `dev-workbook stage <vault path>` command, which copies it to a spool under `${XDG_STATE_HOME:-~/.local/state}/dev-workbook/spool/<session>/` along with the base it was copied from, and the session edits that copy. When the session ends, `SessionEnd` merges its spool into the vault before maintenance and the commit, so the notes get the same frontmatter refresh, index regeneration and owned-paths-only commit as any other session's. A note untouched in the vault meanwhile is replaced. One edited meanwhile is merged three ways with `git merge-file`, and two sessions appending to the same day's log or `ProgressLog.md` both keep their entries. An edit that conflicts is never written: it stays in the spool, and the next session start says where. A spool whose session ended without running its exit hook is applied at the next session start, once its process is gone. The spool accepts only the paths the session-end hook commits, and is never applied mid-merge or mid-rebase.
- **`dev-workbook staged`** lists the staged notes still waiting, and whether each spool is running, due or held on a conflict.
- **`tests/test-vault-spool.py`** covers the staging rules, replace/create/merge, every no-clobber case, the log union rule and when a spool counts as finished. `tests/test-session-end.sh` covers the end-to-end path through the exit and start hooks.

### Changed

- The writing skills (`capture-notes`, `manage-project-workspaces`, `ingest-project-docs`, `summarize-contribution`) stage notes when `CLAUDE_JOB_DIR` is set. `condense-vault` declines to run in a background session, since it renames and deletes notes.

## [3.0.2] — 2026-10-17

### Fixed

- **Closing a session no longer reports `SessionEnd hook [...vault-push.sh] failed: Hook cancelled`.** Claude Code gives all SessionEnd hooks 1.5 seconds by default, and the plugin's own `timeout: 30` does not raise that budget. A push to GitHub over SSH takes about as long on its own, so whenever a session had changes the push was cut off after the local commit, and the next session start pushed it instead. The exit hook now hands the work to a detached background job and returns at once. The job runs in its own process group, so session teardown neither waits for it nor kills it. If it is killed anyway, the next session start still commits and pushes what it left.
- **Index maintenance no longer races the session commit.** Claude Code runs an event's hooks in parallel, so `vault-maintain.sh` could still be rewriting frontmatter while `vault-push.sh` committed, which left the regenerated indexes for the next session. Both now run in order from one hook, `hooks/session-end.sh`.

### Added

- **A session-end lock** (`.git/dev-workbook-end.lock`, never committed). Because the exit work now finishes after Claude Code exits, a session started straight away waits up to 12 seconds for it to finish before committing leftovers or pulling. A second session ending at the same time waits its turn. A lock whose owner has died is taken over, not waited on.
- **`tests/test-session-end.sh`** covers these cases: `--detach` returns well inside the budget, the background push lands even after the hook's process group gets SIGTERM, a failed background push is relayed to the next start, indexes go into the session commit, and the lock is waited on while live and taken over when stale.

## [3.0.1] — 2026-10-15

### Fixed

- **A renamed note is no longer reported as a path outside the vault's known folders.** Git lists a staged rename as two records, the new path and then the old one with no status code; the session-end hook parsed the old path as a status line and cut its first three characters off, so renaming a workspace reported every file in it as unowned (`jects/…`, `tributions/…`). The rename itself was always committed — only the warning was wrong.

## [3.0.0] — 2026-10-15

**claudesidion is now dev-workbook.** The old name tied the plugin to Claude Code and Obsidian; it is a working memory for any coding agent, in any markdown viewer. The vault layout is unchanged — this is breaking only because the plugin's name changed.

### Changed

- **Plugin and marketplace are `dev-workbook@dev-workbook`.** An existing `claudesidion@claudesidion` install stops loading once its marketplace updates; reinstall with the four commands in the README's "Migrating from claudesidion".
- **The command is `dev-workbook`, with `devwb` as a short alias.** There is no `claudesidion` command any more.
- **The vault environment variable is `DEVWB_VAULT`** and the config folder `~/.config/dev-workbook/`.
- **Vault markers are renamed:** `Projects/.dev-workbook-version`, and `.git/dev-workbook-hooks` / `.git/dev-workbook-warnings` inside the vault's git folder.
- **Manifests and README describe the plugin without naming one harness or viewer.**

### Deprecated

- **The pre-3.0 names are still read, after the new ones:** `OBSIDIAN_VAULT`, `~/.config/claudesidion/`, `Projects/.claudesidion-version` (the newer of the two records counts) and `.git/claudesidion-warnings`. They are never written, and stop being read in 4.0.

## [2.6.0] — 2026-10-15

Portability step 4: one session entry point any harness can call.

### Added

- **`claudesidion start` and `claudesidion end`** run the session hooks for harnesses other than Claude Code. `start` prints the combined session context once, in the harness's format: `--format claude` (the default), `cursor` (`{"additional_context": ...}`) or `plain`. Every start hook now emits through one shared function, which also honours `CLAUDESIDION_FORMAT`.
- **Session start commits leftovers.** Changes in the plugin's folders that no session end committed — a harness without one, or a cancelled exit — are committed and pushed at the next session start, before the pull, under the same owned-paths rules as the exit hook.
- **Exit warnings reach the next session.** What the push hook reports at session end (a rejected push, skipped secret-shaped files, paths outside the known folders) was shown to no one. It is now recorded in the vault's `.git` and relayed once by the next session start.

### Fixed

- **A note deleted with `git rm` no longer blocks the session commit.** The push hook ran `git add` on every owned change, which fails outright on an already-staged deletion, and the failure aborted the whole commit — leaving every other change from the session uncommitted. Already-staged changes are now committed without being re-added.

### Changed

- The size check and condense reminder no longer need `jq` when the output format is `plain`.
- `hooks/lib-paths.sh` is now `hooks/lib.sh`, holding the output and warnings helpers alongside path resolution.

## [2.5.0] — 2026-10-15

Portability step 3: skills work when installed on their own, outside the plugin folder.

### Added

- **`claudesidion` command** (`bin/claudesidion`) — one entry point for every tool the skills run: `lint`, `maintain`, `claim`, `rename`, `qualify`, `hours`, `vault-path` and `code-root`. Skills call `claudesidion <command>`, falling back to `python3 "<plugin root>/bin/claudesidion"`. A standalone skill install puts it on PATH with `ln -s <plugin root>/bin/claudesidion ~/.local/bin/`; it finds the rest of the plugin through the symlink.
- **XDG config location.** The vault path and code root are read from `${XDG_CONFIG_HOME:-~/.config}/claudesidion/vault` and `.../code-root` before the legacy `~/.claude/obsidian-vault` and `~/.claude/code-root`, which keep working. Skills now write a newly asked-for vault path to the XDG file.

### Changed

- **One path resolver per language.** The five copies of vault resolution in the hooks are replaced by `hooks/lib-paths.sh`, and the Python one in `rename_note.py` by `hooks/claudesidion_paths.py`; a test checks the two agree case by case.
- **Skills no longer reach scripts by `../../` paths** relative to their own folder.

## [2.4.0] — 2026-10-15

### Added

- **Stale-session guard.** Hooks load when a session starts, so a session begun before a plugin upgrade ran the old maintainer at exit and regenerated indexes in the old format — on 2026-10-12 that brought back 44 pre-2.0 index files. Each session start now records the plugin version in `Projects/.claudesidion-version` (committed with the session, so other machines see it), and a maintenance run older than the recorded version writes nothing. A session start on an out-of-date install is told to update. The guard protects upgrades from 2.4.0 on; hooks from earlier releases do not read the record.
- **`vault_maintain.py --claim`** records the version without maintaining anything; the SessionStart hook uses it.

## [2.3.0] — 2026-10-15

Portability step 2: the vault reads correctly in markdown viewers beyond Obsidian, and the skills behave correctly under harnesses without hooks.

### Added

- **Git sync without hooks.** `vault-pull.sh` writes a heartbeat to `.git/claudesidion-hooks` in the vault at every session start. The skills leave vault git to the hooks while that heartbeat is less than a day old; without one, under a harness that runs no hooks, they pull before their first read and, on close-out, regenerate the indexes and commit and push the same owned paths the push hook would.
- **`table-alias` lint finding** for an aliased wikilink inside a table cell. The alias pipe splits the row into phantom columns in viewers that ignore the `\|` escape.
- **`stacked-keys` lint finding** for `**Key:** value` lines stacked directly under each other. CommonMark viewers (Foam, GitHub) join them into one paragraph; a list item each, or a blank line between, reads right everywhere.
- **`ingest-project-docs` reads every agent's instruction file**: `AGENTS.md`, `GEMINI.md`, `.cursor/rules/` and `.github/copilot-instructions.md` alongside `CLAUDE.md` and `.claude/`.

### Changed

- **TopicIndex letter navigation uses standard anchor links** (`[A](#a)`) instead of Obsidian's heading wikilinks (`[[#A]]`).
- **`qualify_links.py` adds no alias inside a table row**; a cell gets the bare qualified path.
- **Issue items ingested into threads read `issue <n>:`**, not `#<n>`, which viewers parse as a tag.
- **`rename_note.py` rewrites `[[Old.md]]` and links in any letter case**, as viewers resolve them.
- **Skill text is harness- and viewer-neutral**: "agent" rather than "Claude", "markdown vault (Obsidian, Foam, …)" rather than "Obsidian vault". "Obsidian" stays in skill descriptions so existing trigger phrases keep working.
- **`condense-vault` never touches any dot-directory** (`.vscode/`, `.foam/`, not only `.obsidian/`), and `assets/vault-gitignore` ignores VS Code's per-machine state while keeping its settings and Foam's templates tracked.

### Fixed

- **WorkspaceIndex and TimeTracking templates** no longer show aliased links in table cells, and the WorkspaceIndex example links `Overview` rather than the pre-2.0 `Home`.

## [2.2.0] — 2026-10-14

### Fixed

- **Links to log days and structural files no longer point at another project's notes.** Log dates (`2026-10-01`) and structural files (`Overview`, `ProgressLog`, the indexes) repeat in every workspace by design, but the generated indexes linked them bare, and the skills allowed bare links "because Obsidian resolves same-folder first". That rule rarely applies: `ProgressLog.md` and the indexes sit in the workspace root, not in `Log/`, so Obsidian bound those links by its own tie-break, often to another workspace's day. Foam and other viewers refuse to resolve them at all. The generated indexes now write the shortest path that names exactly one note (`[[Alpha/Log/2026-10-01|2026-10-01]]`), and stay bare when a name is unique.
- **`rename_note.py` no longer rewrites another workspace's links.** A path-qualified link such as `[[Log/2026-10-05]]` in workspace B was rewritten when a same-named note in workspace A was renamed, because any link whose folder matched the end of A's path counted as a match. Links are now matched the way a viewer resolves them, by the end of the note's path, and an ambiguous one is rewritten only inside the renamed note's workspace. Rewritten links use the shortest path that names only the moved note.
- **`rename_note.py` moves an untracked note in a versioned vault.** `git mv` refused it after the links had already been rewritten, leaving them pointing at a file that never moved.

### Added

- **`ambiguous-link` lint finding** for a bare log-date or structural-file link that names notes in more than one workspace. Link resolution in the lint is now case-insensitive, matching every viewer.
- **`scripts/qualify_links.py`** — fixes `ambiguous-link` in bulk. Each ambiguous link is resolved against the workspace of the note that contains it and rewritten to that note's shortest unique path, keeping its displayed text as an alias (escaped inside tables). Code, embeds, notes outside workspaces and `Archived/` are untouched; a link with no single candidate in its own workspace is reported, not guessed. `--dry-run` reports the count. `condense-vault` runs it for `ambiguous-link` findings.

### Changed

- **Linking rule:** write the shortest path that names exactly one note. Structural files are always prefixed with the workspace, even from inside it, and log days are prefixed whenever another workspace logged the same date. The templates show the qualified forms.

## [2.1.0] — 2026-10-12

### Added

- **`scripts/rename_note.py`** — renames or moves one vault note and rewrites every reference to it, vault-wide: bare, aliased, table-escaped, heading and path-qualified `[[links]]`, plus `supersedes:`/`superseded_by:` frontmatter in scalar, inline-list and block-list form. It uses `git mv` in a versioned vault and a plain move otherwise. When another note shares the old name, bare links are rewritten only inside the renamed note's workspace. Concurrent calls are serialised with a lock. `--dry-run` reports what would change. It is the tool used for the 2.0 retrofit of a real 11-workspace vault, and `condense-vault` now uses it for every rename and move instead of hand-run `git mv` and link edits.

## [2.0.1] — 2026-10-12

### Fixed

- **The lint now checks `supersedes:` and `superseded_by:` values.** Supersession lives in frontmatter, not in a link, so a rename that rewrote only `[[links]]` left these pointing at names that no longer exist, unreported. They are now `broken-link` findings.

## [2.0.0] — 2026-10-12

### Breaking

- **Every note in the vault is named in PascalCase.** This covers workspace notes (`FrameworkIsFastapiOverDjango`, `VaultPushReliability`, `AdminApiPermissionsAudit`, `DataModelAndCrudPlaybook`, `ACME-1701-NaturalSortAdApprovals`), the structural files (`ProgressLog`, `TopicIndex`, `TicketsIndex`, `DecisionsIndex`, `ThreadsIndex`), the vault-level notes (`Projects/WorkspaceIndex`, `TasksArchive`, `WorkPlanning`), general notes, and the workspace folders themselves (`Projects/Orchard/`). Acronyms are written as words; logs stay `YYYY-MM-DD`; the `# Heading` inside each note is the readable form. The hook now generates the indexes under their new names. **Migrating:** run `condense-vault`. The lint reports every pre-2.0 name (`legacy-name`, `bad-name`), and the reconcile step renames notes, rewrites their links, and removes the stale generated indexes. Until then the skills read the old names.

### Changed

- **Note formats are now specified per type, and the writing style is scan-first.** The old style rule asked for "clarity, not brevity … explanations spelled out", and the workspaces it produced were wordy, inconsistently titled and self-contradicting: logs grew into 5,000-word session diaries, threads into changelogs. Every workspace note is now either **current state** (overview, thread, playbook, decision, research, note, ticket — rewritten in place so it is true today) or **history** (a day's log — one block, merged on a second close-out, never forward-looking). Each type has a template, a naming pattern and, for the short types, a word budget.
- **Next work lives in one place: the Overview's `## Next up`.** Logs no longer carry `Next:` lines, so stale next-work pointers stop accumulating. "What's next" reads `## Next up` first and falls back to the newest log's `Next:` in a workspace that predates this.
- **Editing a note brings it into its template**, and removing or superseding something means fixing the current-state notes that point at it. This replaces "a logging pass is not a cleanup pass".
- **`condense-vault` reconciles before it condenses.** A new first step, run every time and regardless of age, works through the lint findings: strips `Next:` lines from logs (moving anything still open into `## Next up`), merges stacked same-day log blocks, repoints or removes links to superseded decisions, finished threads and deleted notes, renames off-pattern notes, trims over-budget ones and moves stray root files into place.
- **The condense reminder also fires for format findings**, not only for content older than three months.
- **`ingest-project-docs` writes the structured layout.** Its mapping table still pointed at the retired `Open Threads.md` and `Decisions.md` and logged a `Next:` line.

### Added

- **Closing a thread.** A finished or abandoned thread has its decisions, durable knowledge and leftover items moved to their own notes. It is then reduced to a stub (`status: done`, `closed:`, Goal / Outcome / Moved to), which stays so old log links still resolve. The new `unclosed-thread` lint finds threads that are finished but not closed.
- **Optional time tracking.** `TimeTracking.md` is created only when the user asks for it. It holds a phases table (Phase, Status, Estimate, Actual, Variance, Sittings, Dates, Links) and a weekly-hours table, with every other detail linked out. Hours come from the new `scripts/session_hours.py`, which turns Claude Code transcripts into active hours using the method an earlier project developed: only typed messages count, a gap over 15 minutes is a break, and a sitting books under its start date. Unlike that method, it pools concurrent sessions so they are not double-counted. Transcripts expire after 30 days by default, so the table is updated incrementally at each close-out from a `tracked_through:` date. The method is documented in `reference/time-tracking.md`.
- **Playbooks.** A `Playbooks/` folder and `type: playbook` for ordered procedures — phase plans, cutovers, upgrade runbooks, setup guides — with a Goal / Done when / Before you start / Steps / Verify / Gotchas / Out of scope template. An active playbook is its own tracker and is listed in the Threads Index.
- **`vault_maintain.py --lint`** — reports, without writing, every workspace note that breaks the contract: `over-budget`, `root-stray`, `legacy-name`, `unclosed-thread`, `log-next`, `log-stacked`, `stale-link`, `broken-link`, `index-link`, `bad-name`, `dup-name`, `missing-section`, `hard-wrap`. `--lint --count` prints just the number.

### Fixed

- **A `folders` override in `.vault-config.json` no longer hides folders added to the contract later.** The override is merged over the defaults instead of replacing them.

## [1.1.0] — 2026-09-10

### Fixed

- **Vault commits stranded by a cancelled session-end push now reach the remote.** `vault-push.sh` commits locally and then pushes over the network, and Claude Code cancels in-flight hooks during session teardown — reliably enough that the push half was being cut in the gap after the commit half succeeded. The result was the one failure this plugin exists to prevent: commits that exist only on this machine, with no error shown, while the user believes their notes are backed up. `vault-pull.sh` (SessionStart, where there is no teardown pressure) now flushes any commits ahead of the upstream before it pulls, so whatever the last exit stranded goes out at the next launch. A flush that fails is reported as `remain local-only` rather than passing silently.

### Added

- **`tests/test-vault-pull.sh`** — the SessionStart hook had no suite at all. Covers the fail-open preconditions and the flush: stranded commits are pushed and counted, a clean vault claims nothing, a local-only vault with no upstream stays quiet, and an unreachable remote reports the commits as still local rather than as flushed.

## [1.0.1] — 2026-09-07

### Fixed

- **The weekly condense reminder no longer prompts when nothing is stale.** It fired on the 7-day
  stamp alone, so a vault younger than the 3-month staleness threshold was nudged every week into a
  run that could only find nothing. The routine nudge now also confirms at least one file is old
  enough to condense. The "never been recorded" message is deliberately *not* gated — that is how
  someone first learns the routine exists.
- **`stat` platform detection.** The reminder picked BSD vs GNU `stat` with `bsd || gnu`, which does
  not work: GNU `stat` reads the BSD `%Sm` as a *filename*, writes to stderr, and still **exits 0**,
  so the fallback never ran and the check silently found nothing on Linux. It now probes `stat` once
  and tests the output rather than the exit code. Unlike the `date -v`/`date -d` pair, this failure
  mode succeeds wrongly instead of failing cleanly.


## [1.0.0] — 2026-09-07

The flat workspace layout is gone. That transition is what 1.0 was defined as, and it is complete.

### Removed

- **The flat workspace layout.** Workspaces created before 1.0 — stacked `Progress Log.md`,
  `Decisions.md` and `Open Threads.md` — are no longer created, read or written. A workspace is
  now identified solely by its `.vault-config.json`.
- **The `migrate-workspace` skill.** It existed to serve a one-time transition, and that transition
  is done. The plugin now ships five skills.

### Changed

- **A pre-1.0 workspace is reported, not guessed at.** On finding a folder with no
  `.vault-config.json`, the skills say plainly that it is unsupported and tell you to pin to
  `v0.4.x`, run `migrate-workspace`, and upgrade again. They will not read it, will not convert it,
  and will never scaffold a second workspace alongside it.
- **Wikilink conventions are now written down.** A uniquely-named note is linked bare
  (`[[a-decision-note]]`), which survives a workspace being renamed. The six per-workspace
  structural files — `Overview`, `Progress Log`, and the four generated indexes — exist once per
  workspace by design, so links to them carry the workspace prefix (`[[Juniper/Overview]]`)
  whenever they cross a workspace boundary. A bare link resolved against the whole vault binds to
  whichever workspace matches first and *resolves cleanly*, so it reads as healthy while pointing
  at another project's notes.

### Upgrading from 0.x

If every workspace already has a `.vault-config.json`, nothing to do. Otherwise migrate first, on
`v0.4.x`, then upgrade — 1.0 cannot convert for you.


## [0.4.0] — 2026-09-07

### Changed

- **Repo paths in `Projects/_index.md` are now machine-relative.** A row records the repo's path
  relative to that machine's code root, so one row is correct on every machine the vault syncs to.
  The root resolves as `CODE_ROOT`, then `~/.claude/code-root`, then the default `~/code` — the same
  three-tier shape as the vault path, for the same reason. A row starting with `/` is still matched
  literally, so a repo outside the root keeps working.
- **The basename fallback no longer rewrites a row whose recorded path exists on this machine.**
  Previously any path miss rewrote the row, so a repo checked out on two machines had its row
  overwritten by whichever machine ran last — producing a vault diff every session. Rewriting is now
  reserved for a repo that genuinely moved.
- **A total lookup miss no longer scaffolds.** If no row resolves and the index is non-empty, the
  code root is wrong or unset rather than the repo being new. The skill reports which root it
  resolved and stops, instead of creating a second workspace for a repo that already has one.


## [0.3.0] — 2026-09-07

### Changed

- **New workspaces are scaffolded structured.** The flat layout is retired: it is still *read*, so
  status and "what's next" questions work against an existing flat workspace unchanged, but nothing
  new is created in it and nothing is written to it.
- **A write to a flat workspace offers to migrate first.** Accept and it converts with
  `migrate-workspace` then writes; decline and it reports what it would have logged rather than
  appending to the stacked files. It never migrates without asking.
- **The folder skeleton is fixed by the contract**, not configured per workspace. New
  `.vault-config.json` files omit the `folders` key; the maintenance hook now carries the skeleton as
  a built-in default. An explicit `folders` map still overrides it, so workspaces written before this
  keep working. What stays per-project is the vocabulary: `topics`, `min_hits`, `title_weight`,
  `root_notes`.
- Templates, worked examples and the structure contract now show the structured shapes. The flat
  templates are retained and marked retired, for reading existing workspaces.

This is a step toward `1.0`, which lands when the transition is complete and the flat layout is gone.


## [0.2.0] — 2026-09-07

### Changed

- **`condense-vault`'s delete bucket is now scoped by location, not by vault layout.** It applies
  outside project workspaces — `Archived/`, `Inbox/`, `Resources/` and loose root notes. Anything
  under `Projects/<repo>/` is condensed but never deleted: a workspace note records *why* work
  happened and what it touched, which outlives the work itself.

  Previously the bucket was scoped "flat vaults only", which made it dead code in a structured
  workspace and would have made it unreachable entirely once the flat layout is retired. Ticket
  notes are no longer described as the prime delete target — in a workspace they are never deleted
  at all.


## [0.1.0] — 2026-09-07

First tagged release. The plugin has been in single-user daily use for some months; this is the
point at which it became defensible to hand to someone else.

### Added

- Six skills: `capture-notes`, `manage-project-workspaces`, `ingest-project-docs`,
  `summarize-contribution`, `condense-vault`, and `migrate-workspace`.
- Five hooks: session-start vault pull, file-size check, and condense reminder; session-end index
  maintenance and commit/push.
- Structured workspace layout — one note per fact, filed by document type, with generated Topic,
  Tickets, Threads and Decisions indexes. `migrate-workspace` converts a flat workspace to it.
- A regression suite of 122 tests across four suites, run on macOS and Linux in CI, with
  `shellcheck` and `bash -n` gating.
- MIT licence, security policy with private vulnerability reporting, and issue templates.

### Fixed

Everything below was found by four adversarial reviews on 2026-09-03 and fixed before this release.
They are listed because they describe what the plugin used to do to a vault.

- **Data loss and destructive behaviour.** The session-end hook no longer commits while a merge,
  rebase, cherry-pick or revert is in progress, or on a detached HEAD. `git add -A` was replaced
  with an allowlist of plugin-owned paths plus a blocklist of secret-shaped filenames, so a stray
  file elsewhere in the vault is never published on your behalf. Commit and push failures are now
  reported rather than exiting silently, and a failed commit unwinds the index instead of leaving
  the tree staged.
- **Frontmatter round-trip guard, symlink containment, and generated-marker checks** in the index
  maintenance hook, so it cannot write outside the vault or clobber a hand-written index.
- **Bulk deletion in `condense-vault` is gated on the vault being under version control**, since
  git history is what makes a deletion recoverable. An unversioned vault is condensed, never
  deleted from. Cloud-sync revision history is explicitly not accepted as a substitute.
- **Filename handling in the size check** — `-print0` and control-character stripping.
- **Workspace discovery** is no longer pinned to a fixed directory depth, and skips dot-directories.
- **A moved repository** is recognised by basename rather than getting a second workspace.
- **Two test fixtures depended on the developer's global git config** — the bare-remote default
  branch and `--no-identity` — so two guarantees were not actually being tested. Found by running
  the suite on Linux for the first time.

### Security

- Privacy scrub: the working tree and full git history were rewritten to remove an employer domain,
  internal hostnames, real ticket keys, and an internal system name. The repository was then rebuilt
  from a single commit so no pre-scrub object remains reachable.

[Unreleased]: https://github.com/caroline-jeffra/dev-workbook/compare/v3.0.1...HEAD
[1.0.1]: https://github.com/caroline-jeffra/claudesidion/releases/tag/v1.0.1
[1.0.0]: https://github.com/caroline-jeffra/claudesidion/releases/tag/v1.0.0
[0.4.0]: https://github.com/caroline-jeffra/claudesidion/releases/tag/v0.4.0
[0.3.0]: https://github.com/caroline-jeffra/claudesidion/releases/tag/v0.3.0
[0.2.0]: https://github.com/caroline-jeffra/claudesidion/releases/tag/v0.2.0
[0.1.0]: https://github.com/caroline-jeffra/claudesidion/releases/tag/v0.1.0

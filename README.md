# Developer's Workbook

Working memory for coding agents, kept in a plain markdown vault. Skills and session hooks give every repo a durable workspace — what's next, what was decided, what is unfinished — plus notes, imported project context and career-facing contribution summaries.

It runs under Claude Code today, and the vault reads in any wikilink-aware markdown viewer ([Obsidian](https://obsidian.md), [Foam](https://foambubble.github.io/foam/), …). The command is `dev-workbook`, with `devwb` as a short alias. **Formerly `claudesidion`** — see [Migrating from claudesidion](#migrating-from-claudesidion).

## Skills

| Skill | What it does |
|-------|--------------|
| **capture-notes** | Saves general knowledge (ideas, facts, references) as well-formed notes with frontmatter, tags, and wikilinks, in the right folder (`Notes/`, `Resources/`, `Inbox/`). |
| **manage-project-workspaces** | Maintains a per-repo workspace (`Projects/<repo>/`) as the source of truth for "what's next" / "where did we leave off", checked before any issue tracker. One note per fact, filed by type into `Log/`, `Decisions/`, `Threads/`, `Tickets/`, `Research/` and `Notes/`, with generated indexes on top. |
| **ingest-project-docs** | Bootstraps a repo's workspace from context that already exists: open issues/milestones/PRs (GitHub `gh` / GitLab `glab`), in-repo docs (README, `docs/`, agent instruction files such as `CLAUDE.md` and `AGENTS.md`), and scratch files. |
| **summarize-contribution** | Writes or updates a career-facing summary of your contribution to a project, one file per project in `Contributions/`. Evidence comes from git history (identity discovery, authored vs. shipped vs. integrated), the project workspace, and any tracker you have CLI access to. Structured around the project's major efforts, with liftable text for CV, LinkedIn, 360 reviews, and blog topics. Updates integrate into the existing text rather than appending. |
| **condense-vault** | Weekly cleanup: first **reconciles** project workspaces against their note formats whatever their age — strips stale "Next" pointers and stacked entries from logs, repoints or removes links to superseded and deleted notes, renames off-pattern notes, trims over-length ones. Then condenses stale content (untouched >3 months) down to bullet points. Outside the project workspaces — in `Archived/`, `Inbox/`, `Resources/` and loose root notes — it also deletes records of finished work. **Project workspaces are condensed but never deleted from**; a workspace note records why work happened, which outlives the work itself. Deletes only when the vault is a git repository, since git history is what makes a deletion recoverable; an unversioned vault gets condensed instead. |

## Prerequisites

- **macOS or Linux.** The hooks are bash scripts; Windows is supported only under WSL, which is untested.
- **`git`** — for vault version control. Optional: without it the sync hooks do nothing and `condense-vault` condenses rather than deletes.
- **`jq`** — used by the hooks to read hook input.
- **`python3`** — required by the `SessionEnd` maintenance hook. Without it that hook exits silently and indexes are simply not refreshed.
- **A viewer** is optional. The vault is plain markdown on disk with `[[wikilinks]]`; [Obsidian](https://obsidian.md) and [Foam](https://foambubble.github.io/foam/) (VS Code) both read it, and links are written so either resolves them the same way.

## Setup

### 1. Point at your vault

Skills and hooks resolve the vault path in this order:

1. the `DEVWB_VAULT` environment variable, then the pre-3.0 `OBSIDIAN_VAULT`,
2. the config file `~/.config/dev-workbook/vault` (under `$XDG_CONFIG_HOME` if you set it) — one
   line containing the vault's path. Surrounding whitespace is trimmed, and a leading `~/` or
   `$HOME/` is expanded. The pre-3.0 `~/.config/claudesidion/vault` is read next,
3. the legacy config file `~/.claude/obsidian-vault`, read the same way — existing setups keep
   working,
4. the default `~/ObsidianVault`.

**The config file is the recommended way to set it**, because shell-profile exports don't reach
hook shells or non-interactive sessions:

```bash
mkdir -p ~/.config/dev-workbook
echo "$HOME/path/to/your/vault" > ~/.config/dev-workbook/vault
```

The vault can have any name, anywhere on disk (create it first if you don't have one — an empty
folder Obsidian opens works fine). If none of these locations yields an existing directory, the
skills ask where your vault is and write the answer to the config file for you; the hooks stay
silent until it's set.

### 1b. Point at your code (optional)

The workspace index records where each repo lives **relative to a code root**, so one entry is correct on every machine you sync the vault to. The root resolves like the vault path: the `CODE_ROOT` environment variable, then `~/.config/dev-workbook/code-root` (one line), then the pre-3.0 `~/.config/claudesidion/code-root`, then the legacy `~/.claude/code-root`, then the default `~/code`.

```bash
echo "$HOME/code" > ~/.config/dev-workbook/code-root
```

Skip this if your repos are already in `~/code`. A repo living outside the root is recorded with its absolute path instead, so the root never becomes a hard constraint.

Why it exists: an absolute path like `/Users/ada/code/app` is only correct on one machine, and a vault that syncs between two of them ends up with rows that flip back and forth. Storing the machine-specific part once, in config, keeps the vault machine-independent — and keeps your directory layout out of your notes.

### 2. Install the plugin

**As a plugin marketplace** (recommended):

```
/plugin marketplace add caroline-jeffra/dev-workbook
/plugin install dev-workbook
```

This is the only path that installs the **hooks** as well as the skills.

**Or clone and symlink the skills** into your user skills directory:

```bash
git clone https://github.com/caroline-jeffra/dev-workbook.git ~/code/dev-workbook
mkdir -p ~/.claude/skills
for s in ~/code/dev-workbook/skills/*/; do
  ln -s "$s" ~/.claude/skills/
done
mkdir -p ~/.local/bin && ln -s ~/code/dev-workbook/bin/dev-workbook ~/code/dev-workbook/bin/devwb ~/.local/bin/
```

The last line puts the `dev-workbook` command, and its short alias `devwb`, on your PATH. Skills run the plugin's tools (lint,
rename, maintain, hours) through it, and a skill installed outside the plugin has no other way to
find them. `dev-workbook --help` lists its commands.

> [!warning]
> **The symlink path installs no hooks.** You get the skills, but not the vault git sync, the
> file-size check, the condense reminder, or the index maintenance — every hook described under
> "Keeping the vault current across a session" is absent. Without the hooks' heartbeat the skills
> fall back to pulling, committing and pushing the vault themselves, but only when you close out a
> session, and indexes refresh only then too. Use the marketplace install unless you specifically
> want skills-only.

### Other coding agents

The skills are plain Agent Skills and work in any harness that reads them. The session hooks are Claude Code's `hooks/hooks.json`; any other harness gets the same behaviour from two commands, once `dev-workbook` is on your PATH (see the symlink install above):

| Command | Run it at | What it does |
| --- | --- | --- |
| `dev-workbook start --format <claude\|cursor\|plain>` | session start | Relays what the last session's exit reported, commits changes an earlier session left uncommitted, flushes stranded commits, pulls, then runs the size check and the condense reminder. Prints the session context once, in the harness's format. |
| `dev-workbook end` | session end, if the harness has one | Refreshes indexes, commits the plugin's folders, pushes. |

A harness with no session-end event still works: the next `start` commits what the last session left. Whatever `end` reports is also relayed by the next `start`, since few harnesses show session-end output.

### Getting updates

Claude Code does **not** auto-pull marketplace plugins — the marketplace is cached as a git clone and
stays put until you refresh it. After new commits land here, on each machine run:

```
/plugin marketplace update dev-workbook
/reload-plugins
```

`/plugin marketplace update` fetches the latest commits (`/plugin update` alone does not `git fetch`
first and will report "already at latest"); `/reload-plugins` applies them to the current session
without a restart.

Updates are **gated on the version number**, not on new commits: the `version` field in
`plugin.json` is what the marketplace compares against, so you receive a change once that field is
bumped and a release is cut, rather than on every push to `main`.

## Migrating from claudesidion

3.0.0 renamed the plugin from `claudesidion` to `dev-workbook`. **Your vault needs no changes**, but an existing install has to be replaced: once the marketplace updates, the old `claudesidion@claudesidion` entry stops loading.

```
/plugin uninstall claudesidion@claudesidion
/plugin marketplace remove claudesidion
/plugin marketplace add caroline-jeffra/dev-workbook
/plugin install dev-workbook@dev-workbook
```

| Old | New | Old still read? |
| --- | --- | --- |
| `claudesidion` command | `dev-workbook`, alias `devwb` | No — re-create any symlink on your PATH |
| `OBSIDIAN_VAULT` | `DEVWB_VAULT` | Yes, after the new one |
| `~/.config/claudesidion/` | `~/.config/dev-workbook/` | Yes, after the new one |
| `Projects/.claudesidion-version` | `Projects/.dev-workbook-version` | Yes — the newer of the two counts |

Moving your config is optional: `mv ~/.config/claudesidion ~/.config/dev-workbook`. The old names stop being read in 4.0.

## Versioning

This project follows [semantic versioning](https://semver.org). Releases are tagged `vX.Y.Z` and
described in [CHANGELOG.md](CHANGELOG.md).

The public surface being versioned is **not an API** — it is the layout the plugin writes into your
vault and the behaviour of its hooks. So a **major** bump means one of: the workspace structure or
note format changed in a way existing vaults need migrating for; the set of paths the session-end
hook commits changed; or a skill trigger changed so a phrase that used to invoke it no longer does.
New skills, new hooks and additive frontmatter are **minor**.

While the version is `0.x`, **expect breaking changes to the vault layout** between minor versions.
The workspace layout in particular is young; 1.0's removal of the flat layout is the first such
change, and there may be others.

Each release is tagged `vX.Y.Z` in git, and the `version` field in `plugin.json` is bumped to match.
Since updates are version-gated, a commit that does not bump the version does not reach installed
users — which means the changelog and the tag describe exactly what any given update contains.

If an update still isn't reflected after the above, the marketplace cache can be cleared with
`rm -rf ~/.claude/plugins/cache` followed by reinstalling.

## Usage

Once installed and your vault path is set, the skills activate from natural requests in any repo:

- "make a note …" / "capture this" → **capture-notes**
- "what's next" / "where did we leave off" / "log progress" / "record this decision" → **manage-project-workspaces**
- "ingest this project" / "bootstrap the workspace" → **ingest-project-docs**
- "summarize my contribution" / "write a CV summary for this project" / "what should I put on my CV" → **summarize-contribution**
- "condense the vault" / "run the vault cleanup" → **condense-vault**

The vault links *out* to Jira/GitHub/GitLab; it never pushes changes back to them.

### Writing style

Everything written to the vault is **scan-first**: written for someone looking for one fact, not reading start to finish.

- **Answer first** — the first line under any heading is the point.
- **Bullets and `Key: value` pairs over paragraphs**; outcome, not process.
- **One fact, one place** — link the specific note that owns a fact instead of restating it.
- **No stale pointers** — references to finished, superseded or deleted things are removed, not annotated.
- **One continuous line per block** — viewers soft-wrap; hard-wrapped prose reads badly there.

### Note formats

Every workspace note is either **current state** (rewritten in place so it is true today) or **history** (a day's log, append-only and never forward-looking). Next work is stated in exactly one place: the `## Next up` section of the workspace's `Overview.md`.

Each type has a template, a naming pattern and — for the short types — a word budget: logs and decisions 150, overview 200, tickets 250, threads 300. Research opens with a TL;DR; playbooks follow a fixed Goal / Done when / Steps / Verify / Gotchas shape. The full contract is in [`structure.md`](skills/manage-project-workspaces/reference/structure.md) and the templates in [`templates.md`](skills/manage-project-workspaces/reference/templates.md).

**Every note is named in PascalCase**, vault-wide: `FrameworkIsFastapiOverDjango`, `AdminApiPermissionsAudit`, `ACME-1701-NaturalSortAdApprovals`, `ProgressLog`, and workspace folders like `Projects/HomeBudgeter/`. Acronyms are written as words, logs stay `YYYY-MM-DD`, and the `# Heading` inside each note is the readable form.

**A finished thread is closed, not left behind.** Its decisions, knowledge and leftover items move to their own notes, and the thread shrinks to a Goal / Outcome / Moved-to stub.

**Time tracking is optional, per project, and only on request.** `TimeTracking.md` is a phases table (estimate vs actual hours, variance, sittings, dates, links) plus a weekly-hours table. `dev-workbook hours` measures active hours from Claude Code transcripts; see [`time-tracking.md`](skills/manage-project-workspaces/reference/time-tracking.md).

`dev-workbook lint` reports every note that breaks the contract, without changing anything; `condense-vault` works through the findings. Renames go through `dev-workbook rename`, which moves a note and rewrites every link and supersession reference to it; `dev-workbook qualify` rewrites ambiguous links to log days and structural files with their workspace path.

### Workspace layout

A project workspace is **one note per fact**, filed by document type into `Log/`, `Decisions/`, `Threads/`, `Playbooks/`, `Tickets/`, `Research/` and `Notes/`, with an optional `TimeTracking.md`, with `type:`/`status:` frontmatter and generated Topic, Tickets, Decisions and Threads indexes on top. A `.vault-config.json` in the workspace folder marks it as a workspace.

The folder skeleton is **fixed** — every workspace uses the same folder names and document types, so the skills can rely on them. What varies per project is the vocabulary in `.vault-config.json`: the `topics` map and the index tuning (`min_hits`, `title_weight`, `root_notes`).

> [!note]
> **2.0 renamed every note to PascalCase.** A 1.x vault keeps working, because the skills still read the old names. Run `condense-vault` once to rename notes, folders and links, and to remove the stale generated `Topic Index.md`-style files.

> [!warning]
> **1.0 dropped the old flat layout.** Workspaces created before 1.0 — stacked `Progress Log.md`, `Decisions.md` and `Open Threads.md` — are no longer read or written. If you have one, pin the plugin to `v0.4.x`, run its `migrate-workspace` skill to convert it, then upgrade again. This version will tell you rather than guessing, and will never scaffold a second workspace alongside one it cannot read.

### Vault version control

> [!important]
> **This plugin commits and pushes your vault on your behalf.** If your vault is a git repository
> with a remote, work you do in a session is committed and pushed to that remote when the session
> ends, without a further prompt. That is the point of the plugin — but it means anything written
> into an owned folder leaves your machine. Read this section before installing if your vault holds
> anything you would not want pushed, and note the path-allowlist and secret-filename refusals below
> that bound what gets committed.

If your vault is itself a git repository, the plugin syncs it **at the session boundaries, not on
every write**: a `SessionStart` hook pulls it (`git pull --ff-only`) once as the session begins, and a
`SessionEnd` hook commits the session's work as one commit and pushes it. The skills themselves never
touch vault git while the hooks are running — each session start writes a heartbeat to
`.git/dev-workbook-hooks`, and a skill that finds it fresh just writes files. Under a harness with no
hooks (no heartbeat, or one over a day old), the skills pull before their first read and commit and
push the same owned paths when you close out the session.

**What gets committed, and what does not.** The push hook does *not* `git add -A`. It commits only
paths the plugin's conventions own — `Projects/`, `Resources/`, `Contributions/`, and the root
`Home.md`, `TasksArchive.md`, `WorkPlanning.md` — so a stray file elsewhere in the vault is never
published on your behalf. Two further refusals, each reported on stdout rather than done silently:

- **Secret-shaped filenames** (`.env`, `*.pem`, `*.key`, `id_rsa`, `.npmrc`, and similar) are never
  committed, even inside an owned folder. That blocklist cannot be complete, so copy
  [`assets/vault-gitignore`](assets/vault-gitignore) to your vault root as its `.gitignore`.
- **Anything outside those folders** is left uncommitted and named in the hook's output, so you can
  decide what to do with it. `Archived/` is the deliberate exception: it holds retired material the
  plugin does not maintain, so changes there are neither committed nor mentioned.

**When the hook declines entirely.** If the vault has a merge, rebase, cherry-pick or revert in
progress, has unresolved conflicts, or is on a detached HEAD, the hook commits nothing and says why.
Committing in those states would conclude an operation you were in the middle of, or write to a
commit that no branch can reach.

The session commit message is a single short line with no body and no attribution trailer, made on the
current branch (no branching). If the vault is not under version control, both hooks do nothing (they
never run `git init` for you), and a failed pull or push (no remote, offline, auth, conflicts) leaves
the local state and any commit in place rather than erroring.

The one exception is `condense-vault`, which makes its own commit: that run deletes files in bulk, so
it gets a dedicated, recoverable commit rather than being folded into the generic session commit.

### The TasksArchive

`TasksArchive.md` at the vault root is a human-friendly, day-by-day summary — **one line per working
day**, newest month first, with a per-month list of the projects touched. It is the quick-reference to
scan before a personal update meeting, months after the fact; the per-repo `ProgressLog.md` files
remain the detailed record beneath it.

Rows are **terse by design** — two columns (`Date` and `Tasks`), and one short clause per project
touched that day, three to four words each, at a very high level. A ticket number appears only where
it is the shortest identifier. Links stay out of the table cells: an unescaped wikilink alias pipe
breaks the row into phantom columns, and the links crowd out the few words the cell should carry, so
the per-month `Month's Projects` line carries them instead.

The file is created as part of initial setup on first use against a vault, and appended to at session
close.

### Keeping the vault current across a session

The plugin bundles hooks for the vault's git sync, its start-of-session health checks, and its index
maintenance. No hook writes *progress* — ProgressLog entries, decisions and threads are written only
when you ask or say to close out the session (see "When progress gets logged" below). One hook does
write to the vault, though: the `SessionEnd` maintenance hook rewrites derived frontmatter and
regenerates index notes, described below.

- **On session start** (`SessionStart`) — if the vault is versioned, it's pulled (`git pull --ff-only`)
  once as the session begins (and on resume), so the whole session starts from the latest remote
  state. This is the only pull — the skills no longer pull per write.
- **On session start, file-size check** (`SessionStart`) — GitHub warns on files over 50 MB per file
  (and hard-rejects at 100 MB). The hook scans the vault for files within 5% of the warning cap
  (≥ 47.5 MB) and surfaces them so they can be dealt with before a push degrades or fails. The
  remedy is per file and always confirmed with you first: split oversized markdown at a natural
  boundary (per year/month or per topic, updating wikilinks), extract embedded base64 images or
  pasted data dumps into attachment files, or move genuinely binary files to Git LFS.
- **On session start, condense reminder** (`SessionStart`) — the `condense-vault` skill stamps
  `.condense-last-run` in the vault on every run; when that stamp is missing or more than 7 days
  old **and** there is work for it — something stale to condense, or workspace notes that break
  their format — this hook reminds the agent to offer the weekly condense run (it only offers — the
  run never starts unprompted).
- **Background sessions write through a spool** — Claude Code blocks `Write`/`Edit` on a git checkout from a background session, and the vault is one. Instead of switching that protection off, the skills stage each note with `dev-workbook stage <vault path>` and edit the copy it prints, outside the vault. When the session ends, `SessionEnd` merges the staged notes in before maintenance and the commit: a note untouched meanwhile is replaced, one edited meanwhile is merged three ways (appends to the same day's log keep both sides), and an edit that conflicts is never written — it stays staged and the next session start says where. A spool whose session ended without its exit hook running is applied at the next session start. Only the paths the session-end hook commits are accepted. `dev-workbook staged` lists what is waiting.
- **On session end, index maintenance** (`SessionEnd`) — for each workspace that opts in with a
  `.vault-config.json`, this hook fills in derived frontmatter (`project`, `topics`, `tags`) and
  regenerates the Topic, Tickets, Threads and Decisions indexes. It runs *before* the push, so
  regenerated indexes land in the same commit as the notes that changed them. It never deletes or
  moves a file and never edits a note body. Generated indexes carry a `_Generated —` marker and an
  index without that marker is left alone, so a hand-written one is never clobbered; hand-written
  `topics:` are likewise respected. Requires `python3` — without it the hook exits silently.

  **Sessions started before an upgrade leave the vault alone.** Hooks load when a session starts,
  so a session still open from before an upgrade would otherwise regenerate indexes in the old
  format when it exits. Each session start records the plugin version in
  `Projects/.dev-workbook-version`, which the session commit syncs to your other machines, and a
  maintenance hook older than that record does nothing. A session start on an out-of-date install
  says so.

- **On session end** (`SessionEnd`) — if the vault is versioned and the plugin's own folders have
  pending changes, they're committed as one commit and pushed. This is the counterpart to the
  session-start pull, and it's the only place the vault is pushed; if an earlier push failed, it also
  retries any unpushed commits. It commits a selected path list rather than everything in the vault,
  and refuses outright while a merge or rebase is in progress or HEAD is detached — see
  "Vault version control" above. Maintenance, commit and push run in a detached background job,
  because Claude Code allows exit hooks only 1.5 seconds and a push alone can take longer; a
  session started before that job finishes waits for it. Anything it reports reaches the next
  session start.

### When progress gets logged

`manage-project-workspaces` writes to the vault on exactly two triggers:

- **You ask** — "log progress", "record this decision", "update the vault".
- **You close out the session** — "close out the session", "wrap up", "we're done for the day".

On either trigger it does the whole write in one pass: the day's log (merged into one block if the
day already has one), the Overview's `## Next up`, any thread, playbook and decision updates, and the
day's row in `TasksArchive.md`. Nothing is written mid-session while you
work, and no hook nags for it — earlier versions reminded on every `Stop` (i.e. every turn), which
interrupted the coding work it was meant to record. Reading the vault is unrestricted.

Vault reads and writes are also kept out of the transcript: notes are extracted with targeted
`grep`/`sed` rather than read whole, writes are silent, and the agent reports what it wrote in a line
instead of echoing the note — so vault I/O doesn't bury your actual work, even in verbose mode.

All hooks **fail open** — if the vault path is unset, it's not a git repo, or anything goes wrong,
they exit silently and never block or error a turn. They activate automatically once the plugin is
installed via the marketplace; no configuration beyond the vault path is needed.

## Support and bug reports

This is a personal project, maintained in spare time. Issues are read, but there is **no
response-time commitment and no guarantee that any given bug gets fixed**. Bug reports are still
genuinely useful — the plugin was built by one person against one vault, so most of what is wrong
with it is only visible from a vault laid out differently.

- **Found a bug?** [Open an issue](https://github.com/caroline-jeffra/dev-workbook/issues/new/choose).
  The template asks for the commit SHA, how you installed it, and any hook output; those three
  usually settle it.
- **Security problem** — data loss, a secret getting committed, anything written outside your vault?
  Report it privately via the **Security** tab, not a public issue. See [SECURITY.md](SECURITY.md).
- **Pull requests** are welcome but may sit for a while. For anything beyond a small fix, open an
  issue first so the design is agreed before you spend the time.

Two things worth knowing before reporting: the marketplace installs from the branch rather than a
tag, so please give the **commit SHA** as well as the version, and the **symlink install path
installs no hooks**, which accounts for a good share of "the hooks never run" reports.

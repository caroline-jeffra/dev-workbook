# Creating a workspace or a vault-level file

Applies to a write when a workspace or one of the vault-level files is missing: read this before [closeout.md](closeout.md). In a `background=yes` session every note you create is staged first — see [closeout.md](closeout.md).

Read the sections of structure.md that scaffolding needs — `## Structured layout` and `## Naming notes` — with `sed -n '/^## <Heading>/,/^## /p' "<skill dir>/reference/structure.md"`, and take the template for each file from the `templates/` folder named below.

## Step 0 — Ensure the vault-level files exist (once per vault)

Two files live at the **vault root**: `Projects/WorkspaceIndex.md` (the repo → workspace map) and `TasksArchive.md` (see "Maintaining the TasksArchive" in [closeout.md](closeout.md); template in [templates/tasks-archive.md](templates/tasks-archive.md)). A vault from before 2.0 has them as `Projects/_index.md` and `Tasks Archive.md`: read and update the old file in place until `condense-vault` renames it, and never create the new name beside the old one.

**Ask before the first write to a vault that already has content in it.** "What should I work on" is a request to *read*, not consent to create folders in a vault the user may have curated for years. Act on `consent`:

- **`ok`** → create the two files without asking.
- **`ask`** → ask once, naming what you would create and where:

  > This vault has notes in it already. To track work per repo I'd create `Projects/WorkspaceIndex.md` and `TasksArchive.md` at the vault root. Create them?

  If they decline, answer read-only and write nothing. Do not re-ask in the same session.

The same applies in Step 2: scaffolding a **workspace** into an existing `Projects/` folder is a first write to space the user may already be using. Name the folder you are about to create and confirm, unless this plugin created `Projects/` itself. Once either file exists, this step is done and never asks again.

## Step 2 — Scaffold a workspace (first use for a repo only)

**Workspaces are structured.** The flat layout was retired in 1.0 and is no longer created, read or written.

To scaffold:

1. Create `$DEVWB_VAULT/Projects/<Repo>/` — the repo's name in PascalCase (`garden-planner` → `GardenPlanner`) — and, inside it, the folders from [structure.md](structure.md): `Tickets/`, `Epics/`, `Playbooks/`, `Research/`, `Notes/`, `Decisions/`, `Threads/`, `Diagrams/`, `Log/`. **Create each on first use, never empty** — an empty folder is noise in the sidebar and tells the reader nothing.
2. Create `Overview.md` from the template in [templates/overview.md](templates/overview.md) — what the repo is, current focus, next up, the repo path relative to the code root, links to external trackers.
3. Create `ProgressLog.md` (template: [templates/progress-log.md](templates/progress-log.md)) as a **one-line-per-day index**, not a stack of entries. The detail lives in `Log/<date>.md`.
4. Write `.vault-config.json` from the template in [templates/vault-config.md](templates/vault-config.md) — this file is what marks the workspace structured; nothing else does. A new workspace has no content to derive topics from, so start with `"topics": {}` and add them as subjects emerge. The indexes work from day one; the TopicIndex is simply empty until there are topics.

The folder skeleton is **fixed by the contract**, not configured here — every workspace uses the same folder names and the same document types, and skills may rely on that. What stays per-project is the **vocabulary**: `topics`, `min_hits`, `title_weight`, and optionally `root_notes`.

5. Add the row to `WorkspaceIndex.md` (format: [templates/index.md](templates/index.md)). Record the repo's path **relative to the code root** (just `<repo>` for a repo sitting directly in it); use an absolute path only for a repo outside the root.

**Growing the topic vocabulary.** Add a topic once three or four notes would carry it — earlier and it is noise, later and the index has a gap. Each topic needs specific patterns; one matching a common English word tags half the workspace and makes the index useless. After editing `.vault-config.json`, the next session-end hook run re-derives topics across every note.

## The workspace index

### Paths are machine-relative

The vault syncs between machines, and an absolute path is only ever correct on one of them. So a row's path is recorded **relative to that machine's code root**.

**Resolving the code root**, in order: the `CODE_ROOT` environment variable, then `${XDG_CONFIG_HOME:-~/.config}/dev-workbook/code-root` (or the pre-3.0 `…/claudesidion/code-root`), then the legacy `~/.claude/code-root` (one line each, the root's path — whitespace trimmed, a leading `~/` or `$HOME/` expanded), then the default `~/code`; `dev-workbook code-root` prints the result. This is deliberately the same shape as the vault path, for the same reason: profile exports do not reach hook shells.

- **A relative row** (`some-repo`, `nested/some-repo`) resolves against the root. This is the normal form and what you write when adding a repo.
- **An absolute row** (`/opt/src/odd-one`) is matched literally, and is the escape hatch for a repo that does not live under the root. Never rewrite one into a relative path.

When adding a repo, take `git rev-parse --show-toplevel`; if it sits under the resolved root, record the path **relative to the root**, otherwise record it absolute.

### Matching is two-stage

1. **Path match** — resolve each row (relative rows against the root, absolute rows as-is) and compare against the repo's absolute path.
2. **No match** → compare the repo's **basename** against each row's basename and the workspace names.
   - **Exactly one basename match** → check whether that row's recorded path resolves to something that **exists on this machine**.
     - **It does not exist** → the repo moved. Confirm in one line — "`app` is indexed at `code/app`, which is not here — same repo, moved?" — and on confirmation update the row.
     - **It does exist** → do **not** rewrite the row. You are on a different machine from the one that wrote it, or looking at a second checkout; rewriting is how the row ends up ping-ponging between machines on every sync. Use the workspace and change nothing.
   - **Several basename matches** → ask which, listing them. Do not guess.
   - **No basename match** → with no repo rows in the index, genuinely new: scaffold and append a row. With rows that exist on this machine, ask before scaffolding (`dev-workbook context` reports this as `match=unmatched`).

### Never scaffold on a total miss

If **no row resolves at all** and the index is not empty, the code root is wrong or unset — every relative row misses at once. That is a configuration problem, not a new repo.

Say so, name the root you resolved and where it came from, and **stop**. Do not scaffold: creating a workspace here is exactly the split-brain this index exists to prevent, and it is unrecoverable without a manual merge.

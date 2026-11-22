---
name: manage-project-workspaces
description: Maintains a per-repository workspace in the user's markdown vault (Obsidian, Foam, …) as the source of truth for ongoing development work — overview, dated progress log, decisions/ADRs, and open threads. Use when the user asks what to work on next or where a body of work stands — "what's the next task", "what should I work on", "where did we leave off", "what were we doing on this" — as well as "log progress", "record what we did", "record this decision", "track open threads", "close this thread", and — only on request — "set up time tracking", "how many hours has this phase taken". Consult this vault before an issue tracker (Jira/GitHub/GitLab) for next-work questions. Not for "what's the status" in the git sense — uncommitted changes, branch state and diffs come from git, not from here.
---


# Managing project workspaces

Keep a durable, per-repo workspace in the user's markdown vault (Obsidian, Foam, …) so ongoing development work has one findable home, not scattered across trackers, issues and code comments.

**Start here: run `dev-workbook context`.** It prints one `key=value` line (a value with spaces is JSON-quoted, `-` means none). If `command -v dev-workbook` finds nothing, run `python3 "<plugin root>/bin/dev-workbook" context` (the plugin root is two levels above this skill's base directory); a standalone skill needs it on PATH: `ln -s <plugin root>/bin/dev-workbook ~/.local/bin/`.

Keys used below: `vault` (written as `$DEVWB_VAULT` — use this absolute path, as the working directory is usually another repo), `vault_ok`, `vault_from`, `code_root`, `code_root_from`, `repo`, `index`, `index_notes`, `match`, `workspace`, `indexed`, `candidates`, `structured`, `trial`, `consent`, `sync`, `background`. `vault_ok=no` → if `vault_from=env`, say that `DEVWB_VAULT` (or `OBSIDIAN_VAULT`) names a folder that does not exist and stop, since a config file cannot override it; otherwise ask where the vault is and write it to `~/.config/dev-workbook/vault` (creating the folder), then re-run `dev-workbook context` and act only on the new line (no key from the old line carries over).

**Fallback** if the command is unavailable or prints no `match=`: resolve the vault from `DEVWB_VAULT`, then `~/.config/dev-workbook/vault`, then ask; read the index yourself; ask before any first write or scaffold.

## Route by intent

Decide the intent first, then read only the files its route names.

1. **Read** (what's next, where we left off, status) → [reference/read.md](reference/read.md). Reads never scaffold or write: if `match` is `new`, `no-index` or `unmatched`, say there is no workspace and offer `ingest-project-docs`.
2. **Write** (log, record, close out, make a workspace) → when a workspace or vault-level file is missing, read [reference/scaffold.md](reference/scaffold.md) first; a declined consent stops all writes. Then read [reference/closeout.md](reference/closeout.md), which also holds the `background=yes` staging procedure.
3. **Time tracking** (set it up, hours per phase), on request only → [reference/time-tracking.md](reference/time-tracking.md).
4. A request can need several routes ("where did we leave off, then log this"): read each route's file in the order scaffold.md first, then read.md, then closeout.md.

## Step 1 — Locate the workspace

**`WorkspaceIndex.md` is the only way to choose a workspace.** Never pick one by browsing `Projects/` or grepping for a term — a trial or archived copy can look more relevant than the live workspace, because it is the one that has been reorganised. The context line already matched the repo against the index; for `moved` and `unmatched` the matching rules ("Paths are machine-relative", "Matching is two-stage", "Never scaffold on a total miss") are in [reference/scaffold.md](reference/scaffold.md). Act on `match`:

| `match` | Do |
|---|---|
| `path`, `basename` | Use `workspace` and **change nothing** — rewriting a row on another machine is what makes rows ping-pong. |
| `moved` | The recorded path (`indexed`) is missing here, so the repo moved. **Confirm**, then update the row. |
| `ambiguous` | **Ask** which, listing `candidates`. Do not guess. |
| `unmatched` | Also reported when the index has rows the command could not read — then read the index yourself first. Say `repo`, `code_root` and `code_root_from`, and **ask before scaffolding**: a second workspace for an existing repo is the split-brain the index prevents. On a yes, scaffold (Step 2) and add a row. |
| `misconfigured` | No index path exists under `code_root`: the root is wrong or unset. **Stop**, naming `code_root` and `code_root_from`; do not scaffold. |
| `new`, `no-index` | Scaffold (Step 2) and add a row, subject to Step 0 consent; for `no-index` create `WorkspaceIndex.md` first, with the header from [reference/templates.md](reference/templates.md). |
| `no-vault` | Ask where the vault is and re-run, as above. |

If `index_notes=yes` and `match` is not `path`, read the index's notes first.

**Trial workspace.** If `trial` is not `-`, the repo also appears under the index's `## Trial workspaces`: the **main table's row is authoritative**, so write there. Say in one line that `<trial>` also exists as a trial copy and you are writing to the live workspace, so the user can redirect you. **Never write to both**: two workspaces receiving the same entry is the split-brain the trial section exists to prevent. Write to a trial workspace only when the user names it.

## Step 1b — Confirm the workspace is structured

A workspace is structured if it contains `.vault-config.json`; every workspace this version writes to is, since the flat layout was retired in 1.0. If `structured=no`, it predates 1.0 and this version cannot read or write it. Say so plainly and stop:

> `Projects/<name>/` uses the flat layout, which this version no longer supports. Pin the plugin to
> `v0.4.x` and run `migrate-workspace` to convert it, then upgrade again.

Do not read it, do not offer to convert it, and above all do not scaffold a second workspace alongside it.

## Vault git sync

Act on `sync`. The plugin's hooks pull the vault at session start and commit and push it at session end.

- **`hooks`** → **do not run `git pull`, `git add`, `git commit` or `git push` on the vault**; write the files and move on.
- **`self`** → no hooks here, so sync yourself: `git -C "$DEVWB_VAULT" pull --ff-only` before your first read; the commit and push at close-out are in [reference/closeout.md](reference/closeout.md).
- **`none`** → not under version control: nothing to sync, and never `git init` it.

## Keep vault I/O out of the transcript

Vault notes are long prose. Echoing their full text into the transcript buries the actual coding work the user is trying to follow, so **never dump a vault file's contents into the conversation** — not even when the user has the agent running verbose.

- **Reading** — prefer targeted Bash extraction over reading whole files: `grep`, `sed -n '1,40p'`, or an `awk` range that pulls just the section you need (the latest `## YYYY-MM-DD` entry, the unchecked `- [ ]` lines, the "current focus" paragraph). Read a whole file only when you genuinely need all of it.
- **Writing** — append and edit with Bash (`cat >> … <<'EOF'`, `sed -i''`, a small `python3` script) and send any command output to `/dev/null`. A successful write needs no output at all.
- **Reporting** — after writing, say what you did in one short line ("logged today's progress and the archive row"), not by quoting or re-printing what was written. Never print a diff of the note.
- **Verification** — if you must confirm a write landed, check cheaply (`tail -n 3`, a `grep -c`), not by re-reading the file into context.

Reading the vault is unrestricted — read it freely whenever you need context (the read route). The restriction is on *writes*.

## Integrations

Two tools help when they're installed; nothing here depends on them. Detection, rules and formats: [reference/integrations.md](reference/integrations.md).

- **graphify** — when the repo has `graphify-out/graph.json`, answer structural questions while working ("where does X live", "what calls Y") with `graphify query` / `path` before a text search; never build or update a graph yourself.

## Conventions

- Dates: `YYYY-MM-DD`. Tags (if used in frontmatter): lowercase, hyphenated.
- The vault links *out* to Jira/GitHub/GitLab; it does not push changes back to them.

## Templates

The index-note format and a template for every note type are in [reference/templates.md](reference/templates.md).

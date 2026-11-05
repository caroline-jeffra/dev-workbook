---
name: ingest-project-docs
description: Ingests an existing project's documentation and tracker context into the user's markdown vault (Obsidian, Foam, …) workspace — open issues and milestones, open PRs/MRs, in-repo docs (README, docs/, agent instruction files such as CLAUDE.md and AGENTS.md), and temp/scratch files — summarizing each and linking back to the source. Use when starting to track a repo in the vault, or when the user says "ingest this project", "pull in the docs/issues", "bootstrap the workspace", or "import existing context".
---

# Ingesting project docs

Bootstrap a repo's vault workspace from context that already exists — issues, milestones, PRs/MRs,
in-repo docs, and stray working files — so the vault starts as a real source of truth instead of empty.

**Vault location:** resolve in this order — (1) the `DEVWB_VAULT` environment variable (or the pre-3.0 `OBSIDIAN_VAULT`), (2) the config file `${XDG_CONFIG_HOME:-~/.config}/dev-workbook/vault` (or the pre-3.0 `…/claudesidion/vault`), (3) the legacy config file `~/.claude/obsidian-vault`, (4) the default `~/ObsidianVault`. A config file holds one line, the vault's path (whitespace trimmed, a leading `~/` or `$HOME/` expanded); `dev-workbook vault-path` prints the result. If none of them yields an existing directory, ask the user where their vault is and write the answer to `~/.config/dev-workbook/vault` (creating the folder) so every future session and hook finds it. Use the resolved absolute path (written below as `$DEVWB_VAULT`) for every read/write.

**Plugin tools** run through the `dev-workbook` command. If `command -v dev-workbook` finds nothing, run `python3 "<plugin root>/bin/dev-workbook"` instead — the plugin root is two levels above this skill's base directory. A skill installed on its own, outside the plugin, needs the command on PATH: `ln -s <plugin root>/bin/dev-workbook ~/.local/bin/`.

This skill **feeds** the `manage-project-workspaces` structure; it does not invent a new layout.
Read that skill's conventions if unsure where something lands.

## Principles

- **Summarize + link back.** Condense each source into a few lines and link to the original
  (issue/PR URL, or repo-relative file path). The vault stays lean; detail stays at the source.
- **Never clobber.** Read existing workspace files first; append or merge. Ingestion runs may repeat —
  do not duplicate entries already present (match on issue number / file path / title).
- **Report gaps, don't guess.** If a source is unavailable (e.g. a tracker call fails auth), note it
  in the run summary rather than silently skipping it.

## Workflow

Copy this checklist and track progress:

```
Ingest progress:
- [ ] Step 1: Locate/scaffold the workspace
- [ ] Step 2: Detect the forge (GitHub vs GitLab)
- [ ] Step 3: Pull tracker context (issues, milestones, PRs/MRs)
- [ ] Step 4: Gather in-repo docs and temp files
- [ ] Step 5: Map into the workspace
- [ ] Step 6: Report the run
```

**Step 1 — Locate/scaffold the workspace.**
Use `manage-project-workspaces`: find the repo in
`$DEVWB_VAULT/Projects/WorkspaceIndex.md`, or scaffold `Projects/<Repo>/` (PascalCase) and add a row.

**Step 2 — Detect the forge.**
Inspect `git remote -v`. A `github.com` remote → use `gh`. A `gitlab.com` or self-hosted GitLab
remote → use `glab`. If both, ingest from both. Assume the relevant CLI is authenticated; if a call
returns `401`/auth error, record it in the run report and continue with other sources.
Exact commands: see [reference/sources.md](reference/sources.md).

**Step 3 — Pull tracker context.**
Open issues, open milestones, and open PRs/MRs. Keep title, number, URL, labels, and a one-line gist.

**Step 4 — Gather in-repo docs and temp files.**
- Docs: `README*`, `docs/`, any `ARCHITECTURE`/`ADR` files, and every agent instruction file present — `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.claude/` (agents/skills/commands).
- Temp/scratch: untracked or gitignored working files, `TODO.md`, `NOTES.md`, scratchpads
  (`git status --porcelain --ignored` finds them). These are often the richest undocumented context.

**Step 5 — Map into the workspace** (append/merge, never overwrite).

Ingestion always writes, so it always targets a structured workspace — which a newly scaffolded one
is. If the workspace exists but has no `.vault-config.json`, it predates 1.0 and is unsupported:
say so, and write nothing.

See
[manage-project-workspaces/reference/structure.md](../manage-project-workspaces/reference/structure.md)
for the full contract.
- **Overview.md** — seed "What this is" from the README's intro; set trackers (issue/PR URLs); fold in highlights from `docs/` and the agent instruction files as short bullets with links.
- **Threads** — one note per thread of work in `Threads/` (`type: thread`, `status: open`), its open
  issues as `- [ ]` items inside. Group related issues into one thread rather than making a note per
  issue.
- **Playbooks** — a runbook, setup or upgrade guide found in the repo becomes a note in `Playbooks/`
  (`type: playbook`, `status: reference`), summarised to the playbook template with a link back.
- **Next up** — seed `Overview.md`'s `## Next up` with the milestone or thread to pick up first.
- **The day's log** — write `Log/YYYY-MM-DD.md` with the ingestion summary, then add its one-line
  entry to the root `ProgressLog.md`.
- **Decisions** — one note per decision in `Decisions/` (`type: decision`, `status: active`,
  `decided:`), not a stacked `Decisions.md`.
- Write only `type`, `status` and the dates. The `vault-maintain` hook derives `project`, `topics`
  and `tags`, and regenerates the indexes.

Full mapping table and templates: [reference/sources.md](reference/sources.md).

**Step 6 — Report the run.**
Tell the user what was ingested, per source, with counts (e.g. "12 open issues, 3 milestones, 2 open
PRs, README + 4 docs, 1 TODO.md"), and list any source that failed (auth, missing, empty).

## Vault writing style

Two rules govern all markdown written to the vault:

- **No hard line breaks inside a text block.** Each paragraph or bullet is one source line, however long; blank lines separate paragraphs. Viewers soft-wrap to the pane width — never wrap prose to a column width.
- **Scan-first prose.** Write for someone scanning for one fact: the answer first, bullets and `**Key:** value` pairs over paragraphs (at most three short sentences each), outcome rather than process, and a link to the note that owns a fact rather than a restatement of it. Full rules: [capture-notes/reference/conventions.md](../capture-notes/reference/conventions.md).

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

Dates `YYYY-MM-DD`; tags lowercase-hyphenated; link with `[[wikilinks]]` inside the vault and normal
markdown links out to issues/PRs. The vault links *out* to trackers — it does not push back to them.

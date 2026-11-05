---
name: capture-notes
description: Creates well-formed notes in the user's markdown vault (Obsidian, Foam, …) with YAML frontmatter, hyphenated tags, and wikilinks, placed in the right folder. Use when the user says "make a note", "capture this", "save this to my vault/Obsidian", or wants an idea, fact, or reference saved as a durable note (not repo-specific dev work — that is manage-project-workspaces).
---

# Capturing notes

Save general knowledge — ideas, facts, references — as durable notes in the user's markdown vault (Obsidian, Foam, …).

**Vault location:** resolve in this order — (1) the `DEVWB_VAULT` environment variable (or the pre-3.0 `OBSIDIAN_VAULT`), (2) the config file `${XDG_CONFIG_HOME:-~/.config}/dev-workbook/vault` (or the pre-3.0 `…/claudesidion/vault`), (3) the legacy config file `~/.claude/obsidian-vault`, (4) the default `~/ObsidianVault`. A config file holds one line, the vault's path (whitespace trimmed, a leading `~/` or `$HOME/` expanded); `dev-workbook vault-path` prints the result. If none of them yields an existing directory, ask the user where their vault is and write the answer to `~/.config/dev-workbook/vault` (creating the folder) so every future session and hook finds it. Use the resolved absolute path (written below as `$DEVWB_VAULT`) for every read/write.

**Plugin tools** run through the `dev-workbook` command. If `command -v dev-workbook` finds nothing, run `python3 "<plugin root>/bin/dev-workbook"` instead — the plugin root is two levels above this skill's base directory. A skill installed on its own, outside the plugin, needs the command on PATH: `ln -s <plugin root>/bin/dev-workbook ~/.local/bin/`.

This skill runs from any working directory, so always address the vault by its absolute path.
Repo-specific development work (progress logs, decisions, TODOs for a codebase) belongs to the
`manage-project-workspaces` skill, not here.

## Workflow

1. **Decide the note's name.** A concise noun phrase in PascalCase, e.g. `RateLimitingStrategies` —
   acronyms as words (`ApiDesignNotes`), no spaces or punctuation. The filename is `<Name>.md`; the
   `# Heading` is the readable form (`# Rate limiting strategies`).
2. **Pick the folder** (see below). Create it under the vault if it does not exist yet.
3. **Check for an existing note** with that title in the chosen folder. If one exists, edit/append
   rather than overwriting — never clobber existing content.
4. **Write the note** using the template below.
5. **Add wikilinks** to related notes you know exist, and mention likely-related titles as
   `[[wikilinks]]` even if the target does not exist yet (a dangling link is a valid to-do).

## Vault writing style

Two rules govern all markdown written to the vault:

- **No hard line breaks inside a text block.** Each paragraph or bullet is one source line, however long; blank lines separate paragraphs. Viewers soft-wrap to the pane width — never wrap prose to a column width.
- **Scan-first prose.** Write for someone scanning for one fact: the answer first, bullets and `**Key:** value` pairs over paragraphs (at most three short sentences each), outcome rather than process, and a link to the note that owns a fact rather than a restatement of it. Full rules: [capture-notes/reference/conventions.md](reference/conventions.md).

## Keep vault I/O out of the transcript

Vault notes are long prose, and echoing them into the transcript buries the surrounding work. **Never
dump a note's full contents into the conversation** — not even when the agent is running verbose.

Read with targeted Bash extraction (`grep`, `sed -n`, an `awk` range) rather than pulling whole notes
into context; write with Bash appends/edits and send command output to `/dev/null`. Afterwards, report
what you wrote in one short line rather than quoting or diffing it.

## Vault git sync

**Check who syncs first.** The plugin's hooks sync the vault at the session boundaries — on session start one pulls it to latest, and on session end one regenerates the indexes, then commits and pushes everything as a single commit. Each start writes a heartbeat to `.git/dev-workbook-hooks` inside the vault:

```bash
find "$(git -C "$DEVWB_VAULT" rev-parse --absolute-git-dir)" -maxdepth 1 -name dev-workbook-hooks -mmin -1440
```

- **Heartbeat less than a day old** → the hooks are installed. **Do not run `git pull`, `git add`, `git commit` or `git push` on the vault**; write the files and move on.
- **No heartbeat, or an old one** → this harness runs no hooks, so sync yourself: `git -C "$DEVWB_VAULT" pull --ff-only` before your first read, and when the user closes out the session run `dev-workbook maintain`, then stage only the paths the plugin owns (`git -C "$DEVWB_VAULT" add -- Projects Resources Contributions Home.md TasksArchive.md WorkPlanning.md`, skipping any that do not exist), commit them as one single-line commit (`vault: session updates YYYY-MM-DD`) and push. Never `git add -A`, and never commit mid-merge or on a detached HEAD. If the push fails, leave the commit and tell the user.

**Background sessions** (`CLAUDE_JOB_DIR` is set) never write a vault path directly — Claude Code blocks `Write`/`Edit` on the vault's checkout there, and a Bash write would sidestep the protection that block exists for. For each note you would create or change, run `dev-workbook stage "<vault-relative path>"` and do all reading and writing for that note at the path it prints: an existing note is copied there, a new one does not exist yet. Stage each note once. When the session ends, the hooks merge the staged notes into the vault three ways, so edits made there meanwhile survive; a conflicting edit stays staged and the next session reports it. `dev-workbook staged` lists what is waiting. Skip renames and deletions in a background session — leave them for an interactive one.

If the vault is not under version control, there is nothing to sync (and you should never `git init` it).
## Note template

```markdown
---
created: YYYY-MM-DD
tags: [tag-one, tag-two]
---

# <Readable title>

<The note body. Lead with the core idea in one or two sentences, then detail.>

Related: [[AnotherNote]], [[SomeConcept]]
```

- `created`: today's date as `YYYY-MM-DD`.
- `tags`: lowercase, hyphenated, few. Reuse existing tags before inventing new ones — scan the vault
  first (`grep -rh "^tags:" <VAULT> | sort | uniq`).
- `aliases`: add only when the note has genuine alternate names (see reference).

## Folder placement

Keep the tree shallow. Folders answer "where does it live"; tags and links answer "what is it about".

- **`Notes/`** — atomic, evergreen ideas the user is thinking through (the default for original thought).
- **`Resources/`** — reference material: summaries of articles, docs, external facts to look up later.
- **`Inbox/`** — when the right home is genuinely unclear. Capture now, sort later.

Do not write into `Projects/` — that folder is owned by `manage-project-workspaces`.

## Conventions and worked examples

For the full frontmatter field list, tag-vocabulary guidance, aliases, and before/after examples,
see [reference/conventions.md](reference/conventions.md).

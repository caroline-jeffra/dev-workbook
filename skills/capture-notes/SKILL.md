---
name: capture-notes
allowed-tools: Bash(dev-workbook *)
description: Saves an idea, fact or reference as a durable note in the user's markdown vault. Use for "make a note", "capture this", "save this to my vault". Not for repo dev work — that is manage-project-workspaces.
---

# Capturing notes

Save general knowledge — ideas, facts, references — as durable notes in the user's markdown vault.

**Start here: run `dev-workbook context`.** It prints one `key=value` line (a value with spaces is JSON-quoted, `-` means none). If `command -v dev-workbook` finds nothing, run `python3 "<plugin root>/bin/dev-workbook" context` (the plugin root is two levels above this skill's base directory); a standalone skill needs it on PATH: `ln -s <plugin root>/bin/dev-workbook ~/.local/bin/`.

**Links into another skill** (`../<skill>/…`) don't open when this skill is installed on its own: run `dev-workbook ref <skill>/<path>` instead, with `--section <heading>` for one `##` section.

This skill reads `vault`, `vault_ok`, `vault_from`, `sync` and `background`. `vault` is written below as `$DEVWB_VAULT` — use this absolute path for every read and write. `vault_ok=no` → if `vault_from=env`, say that `DEVWB_VAULT` (or `OBSIDIAN_VAULT`) names a folder that does not exist and stop, since a config file cannot override it; otherwise ask where the vault is and write it to `~/.config/dev-workbook/vault` (creating the folder), then re-run `dev-workbook context` and act only on the new line (no key from the old line carries over).

**Fallback** if the command is unavailable or prints no `vault=`: resolve the vault from `DEVWB_VAULT`, then `~/.config/dev-workbook/vault`, then ask. Treat `sync` as `self` if the vault is a git work tree and `none` otherwise, and `background` as `yes` only when `CLAUDE_JOB_DIR` is set.

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

Act on `sync` from the context line. The plugin's hooks pull the vault at session start and commit and push it at session end.

- **`hooks`** → **do not run `git pull`, `git add`, `git commit` or `git push` on the vault**; write the files and move on.
- **`self`** → no hooks here, so sync yourself: `git -C "$DEVWB_VAULT" pull --ff-only` before your first read, and when the user closes out the session run `dev-workbook end`. It refreshes the indexes, commits only the paths the plugin owns (never a secret-shaped file, and nothing already staged outside them) as one single-line commit, and pushes only when every unpushed commit is the plugin's own; it declines mid-merge, mid-rebase or on a detached HEAD. Never commit the vault by hand and never `git add -A`. Relay what it prints; if it reports a push failed or was held back, the commit stays local — tell the user.
- **`none`** → not under version control: nothing to sync, and never `git init` it.

**Background sessions** (`background=yes`) never write a vault path directly — Claude Code blocks `Write`/`Edit` on the vault's checkout there. For each note you would create or change, run `dev-workbook stage '<vault-relative path>'` and read and write it at the path it prints. Stage each note once. The hooks merge staged notes into the vault three ways when the session ends, so edits made meanwhile survive; a conflicting edit stays staged and the next session reports it (`dev-workbook staged` lists them). Skip renames and deletions in a background session.

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

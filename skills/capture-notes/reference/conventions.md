# Note conventions

## Contents
- Writing style
- Frontmatter fields
- Tag vocabulary
- Wikilinks
- Filenames
- Before / after examples

## Writing style

These rules apply to **every markdown file written into the vault**, by any skill.

**No hard line breaks inside a text block.** Each paragraph and each bullet is a single source line, however long; separate paragraphs with a blank line. Markdown viewers soft-wrap to the pane width, so hard-wrapped lines (the 80/100-column habit from code) produce ragged, uncomfortable reading there. Never wrap prose to a column width.

**Scan-first writing.** Every note is written for someone scanning for one fact, not someone reading start to finish:

- **Answer first.** The first line of a note, and the first line under every heading, is the point. Setup and reasoning follow, if at all.
- **Bullets and `**Key:** value` pairs over paragraphs.** A paragraph is at most three short, one-idea sentences in active voice. Never stack `**Key:**` lines directly under each other: CommonMark viewers join them into one paragraph. Make each a list item, or separate them with a blank line.
- **Outcome, not process.** Write what is true or what was concluded — never the story of how you got there.
- **One fact, one place.** Link the note that owns a fact instead of restating it, and link the specific note rather than an index.
- **No stale pointers.** When something is finished, superseded or deleted, remove references to it rather than annotating them ("~~old~~", "update:", "no longer true").
- **Bold only the load-bearing claim.** If everything is bold, nothing is.

Project workspaces add per-type templates and length budgets on top of these rules: see "Writing style" in [manage-project-workspaces/reference/structure.md](../../manage-project-workspaces/reference/structure.md).

## Frontmatter fields

| Field     | Required | Format                        | Notes                                             |
|-----------|----------|-------------------------------|---------------------------------------------------|
| `created` | yes      | `YYYY-MM-DD`                  | Today's date when the note is first written.      |
| `tags`    | yes      | `[a-list, of-tags]`           | Lowercase, hyphenated. Prefer few, reused tags.   |
| `aliases` | no       | `[Alternate Name, Acronym]`   | Only for genuine alternate names the user'd type. |
| `updated` | no       | `YYYY-MM-DD`                  | Add when materially revising an old note.         |

Keep frontmatter minimal. Do not add fields the vault does not already use — extra metadata that
nothing reads is noise.

**Exception — structured project workspaces.** A workspace containing `.vault-config.json` uses a
larger, specified set of fields (`type`, `status`, `topics`, `tickets`, and others) which *are* read:
by the `vault-maintain` hook and by the generated indexes. That contract is defined in
[manage-project-workspaces/reference/structure.md](../../manage-project-workspaces/reference/structure.md).
The rule above still holds everywhere else in the vault, including `Notes/`, `Resources/` and
`Inbox/`.

## Tag vocabulary

- Lowercase, hyphenated, singular where natural: `machine-learning`, `api-design`, `book`.
- Reuse before inventing. List what already exists before adding a tag:
  ```bash
  grep -rhA20 "^tags:" "$DEVWB_VAULT" --include="*.md" \
    | grep -oE "[a-z0-9-]+" | sort | uniq -c | sort -rn
  ```
- 1–4 tags per note is plenty. Tags group notes across folders; they are not a filing cabinet.

## Wikilinks

- Link liberally: `[[NoteName]]`. This is how the vault becomes navigable.
- Link to notes that do not exist yet — a dangling `[[link]]` is a valid "write this later" marker
  and shows up in the viewer's unresolved-links view.
- Prefer linking over duplicating: reference `[[RateLimitingStrategies]]` instead of restating it.
- Use display text when the flow needs it: `[[RateLimitingStrategies|rate limiting]]`.

## Filenames

- `<Name>.md` in **PascalCase**, like every note in the vault: `CacheInvalidationApproaches.md`. Acronyms are words (`ApiDesign`, not `APIDesign`); no spaces, hyphens or punctuation.
- The `# Heading` inside is the readable form: `# Cache invalidation approaches`.
- No dates in general-note filenames (dates live in frontmatter). Dated filenames are for logs, which
  are the `manage-project-workspaces` skill's job.

## Before / after examples

**Bad (vague, no structure):**
```markdown
some thoughts on caching. use redis maybe. TTL important.
```

**Good:**
```markdown
---
created: 2026-07-10
tags: [caching, system-design]
---

# Cache invalidation approaches

Cache invalidation is the hard part of caching. Three common strategies: **TTL expiry**, **write-through**, and **explicit purge** on mutation. TTL is the simplest, but it serves stale data within the expiry window.

Related: [[RateLimitingStrategies]], [[Redis]]
```

**Reference note (summarizing an external source):**
```markdown
---
created: 2026-07-10
tags: [book, productivity]
aliases: [GTD]
---

# Getting things done

Core idea: capture everything into a trusted system, then process each item into a concrete next action. A weekly review is what keeps the system trustworthy.

Source: David Allen, *Getting Things Done*.

Related: [[InboxZero]]
```

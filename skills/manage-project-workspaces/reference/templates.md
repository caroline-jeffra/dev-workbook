# Workspace templates

## Contents
- Index note (`Projects/WorkspaceIndex.md`)
- Overview.md · ProgressLog.md · Log · TimeTracking.md (optional)
- Thread · Playbook · Research · Ticket · Decision · Note
- `.vault-config.json`
- `TasksArchive.md`

## Index note (`Projects/WorkspaceIndex.md`)

Maps each repo to its workspace folder. Header + one row per repo:

```markdown
---
created: YYYY-MM-DD
tags: [index]
---

# Project Workspaces

| Repo path | Workspace |
|-----------|-----------|
| some-repo | [[SomeRepo/Overview]] |
| /opt/src/odd-one | [[OddOne/Overview]] |
```

The Workspace cell is a plain link to the workspace's `Overview` — never aliased, since an alias pipe splits the row in viewers that ignore the `\|` escape.

### Paths are machine-relative

The vault syncs between machines, and an absolute path is only ever correct on one of them. So a
row's path is recorded **relative to that machine's code root**.

**Resolving the code root**, in order: the `CODE_ROOT` environment variable, then
`${XDG_CONFIG_HOME:-~/.config}/dev-workbook/code-root` (or the pre-3.0 `…/claudesidion/code-root`), then the legacy `~/.claude/code-root` (one
line each, the root's path — whitespace trimmed, a leading `~/` or `$HOME/` expanded), then the
default `~/code`; `dev-workbook code-root` prints the result. This is deliberately the same shape as
the vault path, for the same reason: profile exports do not reach hook shells.

- **A relative row** (`some-repo`, `nested/some-repo`) resolves against the root. This is the normal
  form and what you write when adding a repo.
- **An absolute row** (`/opt/src/odd-one`) is matched literally, and is the escape hatch for a repo
  that does not live under the root. Never rewrite one into a relative path.

When adding a repo, take `git rev-parse --show-toplevel`; if it sits under the resolved root, record
the path **relative to the root**, otherwise record it absolute.

### Matching is two-stage

1. **Path match** — resolve each row (relative rows against the root, absolute rows as-is) and
   compare against the repo's absolute path.
2. **No match** → compare the repo's **basename** against each row's basename and the workspace
   names.
   - **Exactly one basename match** → check whether that row's recorded path resolves to something
     that **exists on this machine**.
     - **It does not exist** → the repo moved. Confirm in one line — "`app` is indexed at
       `code/app`, which is not here — same repo, moved?" — and on confirmation update the row.
     - **It does exist** → do **not** rewrite the row. You are on a different machine from the one
       that wrote it, or looking at a second checkout; rewriting is how the row ends up
       ping-ponging between machines on every sync. Use the workspace and change nothing.
   - **Several basename matches** → ask which, listing them. Do not guess.
   - **No basename match** → genuinely new. Scaffold and append a row.

### Never scaffold on a total miss

If **no row resolves at all** and the index is not empty, the code root is wrong or unset — every
relative row misses at once. That is a configuration problem, not a new repo.

Say so, name the root you resolved and where it came from, and **stop**. Do not scaffold: creating a
workspace here is exactly the split-brain this index exists to prevent, and it is unrecoverable
without a manual merge.

## Overview.md

Current state. Rewrite in place on every close-out so it is true today. Budget: 200 words.

```markdown
---
type: overview
status: active
---

# <repo>

**Repo path:** `<path relative to the code root>`

**Current focus:** <one line — what the work is right now>

## Next up

- <the next concrete step> — [[<ThreadOrPlaybook>]]
- <at most five bullets, most urgent first; remove a bullet the moment it is done>

## What this is

<Two or three sentences: what the codebase does, why the user is working on it.>

## Trackers

- Jira: <url or n/a>
- GitHub/GitLab: <url or n/a>

## Map

- [[<Workspace>/ProgressLog|ProgressLog]] · [[<Workspace>/TopicIndex|TopicIndex]] · [[<Workspace>/DecisionsIndex|DecisionsIndex]] · [[<Workspace>/ThreadsIndex|ThreadsIndex]]
```

`## Next up` is **the only place next work is stated** in a workspace. Each bullet names one action and links the thread or playbook holding the detail.

## ProgressLog.md

An **index**: one line per working day, newest first. The detail lives in `Log/YYYY-MM-DD.md`. Never append a dated section to this file.

```markdown
---
type: log-index
status: reference
---

# Progress log — <repo>

One line per working day. Detail lives in the dated note.

- **[[<Workspace>/Log/YYYY-MM-DD|YYYY-MM-DD]]** — <one-line headline of the day, ≤ 12 words>
```

## Log — `Log/YYYY-MM-DD.md`

History. One block per day; a later close-out the same day **merges into these sections**. Budget: 150 words. **No `Next:` line** — next work goes in `Overview.md`'s `## Next up`.

```markdown
---
type: log
date: YYYY-MM-DD
---

# YYYY-MM-DD

- **Did:** <what changed — outcomes, one clause each, semicolon-separated>
- **Decided:** [[<DecisionNote>]] <omit the line if nothing was decided>
- **Learned:** <what you now know that you did not before; omit if nothing>
- **Case study:** <what happened, one clause> — `production-incident` `owned-mistake` · failure <omit unless the work matched a prompt in Contributions/CaseStudyPrompts.md; one line per story>
- **Links:** [[<ThreadOrPlaybook>]], PR <url>
```

## Thread — `Threads/<NounPhrase>.md`

Current state. Budget: 300 words. Done items collapse to one line each with no date or narrative; when nothing is open, set `status: done` and remove it from `## Next up`.

```markdown
---
type: thread
status: open
tickets: []
---

# <Thread name in sentence case>

**Goal:** <one line — what "finished" looks like>

## Open

- [ ] <action> — <one-line context if needed> ([ACME-123](url))

## Done

- [x] <action>
```

**Closing it** — when the last item is ticked, or the user says it is done or abandoned, follow "Closing a thread" in [structure.md](structure.md): move decisions, durable knowledge and leftover items to their own notes, then reduce the thread to this stub.

```markdown
---
type: thread
status: done
closed: YYYY-MM-DD
---

# <Thread name in sentence case>

**Goal:** <the original goal>

**Outcome:** <one line — shipped, or abandoned and why>

**Moved to:** [[<DecisionNote>]], [[<Note>]], [[<OtherThread>]]
```

## Playbook — `Playbooks/<Area><Subject>.md`

Current state: the plan **and** its tracker. Tick steps in place as they finish; do not mirror them into a thread. `status: active` while being executed, `done` when finished, `reference` for a procedure you re-run (a setup guide, a cutover runbook).

~~~markdown
---
type: playbook
status: active
tickets: []
---

# <Subject in sentence case>

**Goal:** <one line — the outcome this playbook produces>

**Done when:** <checkable condition — a command that passes, a URL that serves, a state you can observe>

## Before you start

- <prerequisite or access needed>
- <decision to make first> — [[<DecisionNote>]] once made

## Steps

- [ ] **1. <Step title>** (~<estimate>) — <one line on what and why>
  - `<command>` or <sub-action>
- [ ] **2. <Step title>** (~<estimate>) — <one line>

## Verify

```bash
<the commands that prove "done when">
```

## Gotchas

- **<Trap>** — <how to avoid it>

## Out of scope

- <what this playbook deliberately does not do, and where it lives instead>
~~~

- **Steps are actions, not essays.** One line each; sub-bullets only for the commands or sub-actions needed to carry it out. Reasoning belongs in a linked decision or research note.
- **Decisions do not live in the playbook.** "Before you start" names them; once made, each becomes a decision note and the bullet links it.
- **No outcome narration on ticked steps.** `- [x] **3. Alembic init**` is complete. What happened goes in the day's log.

## Research — `Research/<Subject><Kind>.md`

Current state. No length budget, but the TL;DR is mandatory: a reader who stops after it must have the answer.

```markdown
---
type: research
status: reference
tickets: []
---

# <Subject in sentence case> — <kind>

## TL;DR

- <the conclusion>
- <the second most important finding>
- <what it means for the work — link the decision or playbook it fed>

## <Section per question answered>

<Findings as bullets and tables. Evidence links inline.>

## Sources

- <url or repo path>
```

`<Kind>` is one of `Audit` · `Analysis` · `Plan` · `Spec` · `Review` · `Map` · `Reference` — e.g. `AdminApiPermissionsAudit.md`, heading `# Admin API permissions — audit`.

## Ticket — `Tickets/<number>-<Subject>.md`

The project key stays in `tickets:` and the heading; the file name carries only the number, so the subjects line up in a sorted list. `ACME-1234` → `Tickets/1234-NaturalSortAdApprovals.md`.

Current state. Budget: 250 words.

```markdown
---
type: ticket
status: active
tickets: [ACME-1234]
---

# ACME-1234 <short subject>

**Goal:** <one line>

**Status:** <one line — where it stands now>

## Findings

- <what was learned that outlives the ticket>

## Links

- Ticket: <url> · PR: <url>
- [[<RelatedResearchDecisionOrPlaybook>]]
```

## Decision — `Decisions/<ClaimInPascalCase>.md`

Current state (until superseded). Budget: 150 words.

```markdown
---
type: decision
status: active
decided: YYYY-MM-DD
tickets: []
---

# <Claim in sentence case>

**Decision:** <one sentence — the rule now in force>

**Why:** <one or two sentences>

**Rejected:** <alternative> — <one-line reason>; <alternative> — <reason>

**Source:** [[<Workspace>/Log/YYYY-MM-DD|YYYY-MM-DD]] <or the research note it came from>
```

A **convention** uses the same shape with `type: convention`, no `decided:`, and `**Rule:**` in place of `**Decision:**`.

## Note — `Notes/<NounPhrase>.md`

Current state. Lead with the fact or technique in one line; the rest supports it.

```markdown
---
type: note
status: reference
---

# <Title in sentence case>

<The fact or technique, in one or two sentences.>

- <supporting detail>
- <example or command>

Related: [[<OtherNote>]]
```

## TimeTracking.md — optional, on request only

A summary table and nothing else: every number links to where its detail lives. Created only when the user asks for time tracking; the method and the script behind the numbers are in [time-tracking.md](time-tracking.md).

```markdown
---
type: time-tracking
status: active
tracked_through: YYYY-MM-DD
---

# Time tracking — <repo>

**Budget:** <N> hrs/week · ~<N> hrs by <deadline> — [[<BudgetDecision>]]

## Phases

| Phase | Status | Estimate | Actual | Variance | Sittings | Dates | Links |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Planning | done | — | 3.37 | — | 8 | 08-15 | [[Juniper/Log/2026-08-15]] |
| **0 Walking skeleton** | done | 12 | 7.89 | −34% | 6 | 08-16 → 08-19 | [[WalkingSkeleton]] |
| 0.1–0.5 Scaffold and CI | done | 4 | 2.25 | −44% | 1 | 08-16 | [[Juniper/Log/2026-08-16]] |
| **1 Data model and CRUD** | active | 25 | 11.13 | — | 13 | 08-23 → | [[DataModelAndCrud]] |
| **Total** | | 165 | 22.39 | | 28 | | |

## Weekly hours

| Week | Weekday | Weekend | Total | vs budget |
| --- | --- | --- | --- | --- |
| Aug 17–23 | 6.24 | 0.80 | 7.04 | within |
```

- **Phase rows in bold, subphase rows plain** directly beneath their phase. Add subphase rows only for subphases with their own estimate.
- **Hours as decimals**, two places. Estimates as the plan wrote them.
- **Status** is `planned`, `active`, `done` or `dropped`.
- **Variance** only once a row is `done`: `(actual − estimate) / estimate`, as a signed whole percent. Rows without an estimate (planning, project management) show `—`.
- **Dates** as `MM-DD`, with an open arrow (`08-23 →`) while active.
- **Links** point at the playbook for a phase and the log or PR for a subphase. Analysis of the numbers, such as estimate accuracy, goes in a `Research/` note linked from the budget line, never in this file.
- **vs budget** is `under`, `within` or `over`, against the weekly hours on the budget line.
- `tracked_through:` is the last day whose sessions are counted, so the next update starts from the day after.

## `.vault-config.json`

Written at scaffold time; this file is what marks a workspace structured.

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

The folder skeleton is fixed by the contract and is not configured here. What varies per project is
the vocabulary: `topics`, `min_hits`, `title_weight`, and optionally `root_notes`.

## `TasksArchive.md` (vault root — create once per vault)

Lives at `$DEVWB_VAULT/TasksArchive.md`, not inside a workspace. Seed it with the frontmatter and
intro only; months and rows get appended as work happens.

```markdown
---
created: <YYYY-MM-DD>
tags: [index, archive]
---

# Tasks archive

One line per working day, newest year first. This is the quick-reference for personal update meetings — scan a month, recall what you shipped.

Rows are deliberately **terse**: one short clause per project touched that day, three to four words each, at a very high level. No links inside table cells — the `Month's Projects` line above each table is where the project links live, and all detail lives in each project's `ProgressLog`.

# <YYYY>

## <Mon YYYY>

### Month's Projects
[[<project>/Overview|<project>]]

| Date | Tasks |
| ---- | ----- |
| <d>  | <one 3–4 word clause per project touched, comma-separated, no links> |
```

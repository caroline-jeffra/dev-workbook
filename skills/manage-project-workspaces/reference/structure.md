# Workspace structure contract

Every workspace uses the structured layout: one note per fact, filed by document type, with derived metadata in frontmatter. The flat layout was retired in 1.0.

## Detecting the layout

A workspace is valid if it contains `.vault-config.json`. A workspace without one predates 1.0 and is **not supported** — it can neither be read nor written. Tell the user to pin to `v0.4.x`, run `migrate-workspace`, and upgrade again.

```bash
[ -f "$WORKSPACE/.vault-config.json" ] || echo "unsupported pre-1.0 workspace"
```

Never guess from the presence of a folder — only `.vault-config.json` marks a workspace.

---

## Two kinds of note: current state and history

**Every note is either true now, or a record of a day. Never both.** Mixing the two is what turns a workspace unreadable: a thread that narrates when each box was ticked, a log whose `Next:` line was overtaken a week ago, an overview that still names last month's focus.

| Kind | Types | Rule |
| --- | --- | --- |
| **Current state** | overview, thread, playbook, decision, convention, research, note, ticket, epic | **Rewrite in place** so the note is true today. No dated history inside — git keeps that. Remove what is finished or wrong; do not annotate it. |
| **History** | log | **Append-only and backward-looking.** Records what happened that day. Never carries `Next:` or any other forward-looking line. |

**"What's next" lives in exactly one place:** the `## Next up` section of `Overview.md`, each bullet linking the thread or playbook that holds the detail. Nothing else states next work — not logs, not research, not decisions.

---

## Structured layout

### Root — the contract files only

Nothing else goes in the workspace root. Plans, roadmaps and guides belong in a folder; a CV summary belongs in the vault's `Contributions/`; a `Home.md` duplicates `Overview.md` and must not exist.

| Note | What it is | Who writes it |
| --- | --- | --- |
| `Overview.md` | What the repo is, current focus, **next up**, trackers | you |
| `ProgressLog.md` | One line per working day, linking to `Log/<date>.md` | you |
| `TopicIndex.md` | Every topic A–Z with the notes under each | **generated — never hand-edit** |
| `TicketsIndex.md` | Every ticket and the notes mentioning it | **generated — never hand-edit** |
| `DecisionsIndex.md` | Decisions and conventions grouped by status | **generated — never hand-edit** |
| `ThreadsIndex.md` | Threads and active playbooks, most open items first | **generated — never hand-edit** |
| `TimeTracking.md` | **Optional** — hours per phase against estimates; created only when the user asks for time tracking | you — see [time-tracking.md](time-tracking.md) |

A workspace may whitelist extra root notes in `.vault-config.json` (`root_notes`), but new workspaces should not need to.

### Folders — filed by document type

| Folder | `type:` | What belongs there |
| --- | --- | --- |
| `Tickets/` | `ticket` | Work scoped to one tracker ticket; done when it ships |
| `Epics/` | `epic` | A multi-ticket body of work tracked as such |
| `Playbooks/` | `playbook` | An ordered procedure to follow: phase plans, cutovers, upgrade runbooks, setup guides |
| `Research/` | `research` | Investigations that outlive the ticket: audits, analyses, specs, reviews, maps |
| `Notes/` | `note` | Durable cross-ticket knowledge; reusable techniques |
| `Decisions/` | `decision`, `convention` | One note per decision or standing convention |
| `Threads/` | `thread` | One note per thread of unfinished work; closed when finished (see "Closing a thread") |
| `Log/` | `log` | One note per working day: `Log/YYYY-MM-DD.md` |

### Choosing the type

- **`playbook` vs `research`** — will someone *follow it step by step*? → `playbook`. Does it *explain or assess* something? → `research`. A plan that weighs options is research; the ordered steps that carry the chosen option out are a playbook.
- **`playbook` vs `thread`** — a playbook being executed **is** the tracker for that work: tick its steps in place. Do not also open a thread that repeats the same steps — two lists of the same work drift apart and contradict each other.
- **`ticket` vs `research`** — will this note still be useful after the ticket ships? Yes → `research`.
- **`note` vs `research`** — did it require investigation to produce? Yes → `research`. Is it a technique or a fact you will cite later? → `note`.
- **`decision` vs `convention`** — was it decided on a date, in response to something? → `decision`. Is it a standing norm with no decision event? → `convention`.

### When a ticket earns its own note

Not every ticket needs one. A ticket gets a note when there is something to say that outlives a checkbox — findings, a plan, deferred gaps, review comments. A ticket that is just a unit of work lives as a `- [ ]` item inside the relevant thread or playbook. Follow what the workspace already does.

---

## Naming notes

**Every note in the vault is named in PascalCase** — workspace notes, the structural files, general notes outside `Projects/`, and the workspace folders themselves. The only exceptions are log dates and the ticket number at the front of a ticket note.

**Names are built to be skimmed in a sorted, truncated file list.** The folder already says which project and which type a note is, so the name spends its first characters on what tells notes apart: **area first, kind last** — `<Area><Subject><Kind>`. The area is the subsystem or feature (`Currency`, `CrossSell`, `Docker`), so related notes sort together across folders and a truncated name still shows it.

| Type | Pattern | Example |
| --- | --- | --- |
| decision, convention | a **claim**, 4–8 words, **subject first** | `FrameworkIsFastapiOverDjango`, `RedisMultiExcludesDbQueries` |
| thread | `<Area><Subject>`, 2–4 words, optionally ending `FollowUps` · `Blocker` · `Backlog` | `VaultPushReliability`, `CurrencyCacheFollowUps` |
| playbook | `<Area><Subject>`, no suffix | `DataModelAndCrud`, `PhpstanBaselineFix` |
| research | `<Area><Subject><Kind>`, Kind ∈ `Audit · Analysis · Plan · Spec · Review · Map · Reference` | `AdminApiPermissionsAudit` |
| note | `<Area><Subject>`, optionally ending `Gotchas` · `Findings` · `Diagnosis` | `PostgresAdvisoryLocks`, `DockerLocalEnvGotchas` |
| ticket | `<number>-<Subject>` — the key stays in `tickets:` | `1701-NaturalSortAdApprovals` |
| log | `YYYY-MM-DD` | `2026-08-19` |
| structural | fixed | `Overview`, `ProgressLog`, `TopicIndex`, `TicketsIndex`, `DecisionsIndex`, `ThreadsIndex`, `TimeTracking` |
| vault root | fixed | `Projects/WorkspaceIndex`, `TasksArchive` |
| workspace folder | the repo's name | `Projects/HomeBudgeter/` (and `Contributions/HomeBudgeter.md`) |

- **Acronyms are words.** `AdminApiAudit`, `CiPipelineSpec`, `SqlInjectionAudit` — never `AdminAPIAudit`, which hides the word boundary.
- **No spaces, hyphens, underscores or em dashes** — except the one after a ticket note's number.
- **Never the project's name.** `Projects/Bert/Research/DataFlowsMap.md`, not `BertDataFlowsMap.md` — the folder says it, and the prefix pushes the subject out of view. The lint reports one.
- **Never the folder's type.** A playbook is not `…Playbook`; a ticket is not `BERT-1234-…`. Research keeps its Kind, because Audit, Plan and Spec tell research notes apart.
- **Decisions lead with their subject, not a verb.** `RedisMultiExcludesDbQueries`, not `RunDbQueriesOutsideRedisMulti` — verb-first claims scatter across the alphabet and never group.
- **Two to four words** for everything but decisions. Anything longer is truncated in a sidebar anyway.
- **Numbers stay digits:** `Laravel13UpgradePlan`, `Phase2Ingestion`.
- **No dates in names** except logs. A review of a playbook is `IngestionReview`, not `Phase 2 Playbook Review 2026-10-02`; the date goes in frontmatter.
- **Ticket numbers prefix ticket notes only.** A research note about a ticket carries the ID in `tickets:`, not in its name.
- **Name what it is, not where it falls.** `Phase1` says nothing in a year; name what the phase does.
- **Names must be unique within their workspace**, and general notes outside `Projects/` unique across the vault. Two workspaces may share a name (`Bert/Threads/CompletedItems`, `Watson/Threads/CompletedItems`); links to such a note carry the workspace path — see "Linking between notes". The lint reports a bare link to a shared name as `ambiguous-link`.
- **The `# Heading` is the readable form**, in sentence case with normal spacing and acronyms: `FrameworkIsFastapiOverDjango.md` has the heading `# Framework is FastAPI over Django`. The generated indexes display the heading, so lists stay readable.

---

## Writing style

Every note is written for **someone scanning for one fact**, not someone reading start to finish.

- **The first line under any heading is the answer.** Setup and reasoning come after, if at all.
- **Bullets and `**Key:** value` pairs over paragraphs.** A paragraph is at most three short sentences. Never stack `**Key:**` lines directly under each other: CommonMark viewers join them into one paragraph. Make each a list item, or separate them with a blank line.
- **Outcome, not process.** Write what is true or what was decided — never "first I tried X, then Y". Dead ends earn one bullet in a log's `Learned`, not a narrative.
- **One fact, one place.** Link the note that owns a fact instead of restating it. Link the **specific** note — `[[FrameworkIsFastapiOverDjango]]`, never `[[DecisionsIndex|the decisions]]`.
- **No stale pointers.** When something is finished, superseded or deleted, remove references to it from current-state notes rather than annotating them ("~~old plan~~", "now done", "see update below").
- **No commit SHAs, step numbers or session narration** in current-state notes. Link a PR if the provenance matters.
- **One continuous line per block** — no hard line breaks inside a paragraph, bullet or blockquote. Viewers soft-wrap.
- **Bold only the load-bearing claim.** If everything is bold, nothing is.

### Length budgets

Body words, excluding frontmatter and fenced code. The `vault-maintain` lint flags notes over budget; the fix is to cut, link out, or split — never to raise the budget for one note.

| Type | Budget |
| --- | --- |
| log | 150 |
| decision, convention | 150 |
| overview | 200 |
| ticket | 250 |
| thread | 300 |
| playbook, research, note, epic | no budget — but research must open with a `## TL;DR` and a playbook must follow its template |

Templates for every type are in [templates.md](templates.md).

---

## Linking between notes

`[[target]]` names every note whose vault path ends with `target`, compared case-insensitively — Obsidian, Foam, Quartz and the markdown language servers all agree on that. **Write the shortest path that names exactly one note.**

| Target | Write | Why |
| --- | --- | --- |
| A note in any type folder | `[[NoteName]]` | Names are unique within a workspace; a bare link survives a workspace rename |
| A note whose name another workspace also uses | `[[Workspace/NoteName]]` | The bare name is ambiguous vault-wide |
| `Overview`, `ProgressLog`, or any generated index | `[[Workspace/Overview]]`, even from inside that workspace | These exist once per workspace by design, so the bare name is ambiguous vault-wide |
| A log day whose date another workspace also logged | `[[Workspace/Log/2026-10-04\|2026-10-04]]` | Workspaces often log the same day; the alias keeps the date readable |
| Any link inside a table cell | `[[Workspace/Log/2026-10-04]]` — no alias | An alias pipe splits the row in viewers that ignore the `\|` escape |

Wikilinks have **no `../` syntax** — a vault-relative path is the only disambiguator. There is no same-folder exception: viewers disagree on tie-breaks, so an ambiguous link is wrong even where it happens to land right. The lint reports one as `ambiguous-link`; `scripts/qualify_links.py` fixes them in bulk.

**The failure this prevents.** A bare `[[Decisions]]` resolved against the whole vault binds to whichever workspace matches first. It resolves *successfully*, so "do the links work?" reports healthy while the link points at a different project's notes. Silent cross-project links are worse than broken ones: a broken link is noticed, a wrong one is trusted.

## Frontmatter contract

### Fields you write

| Field | Required | Values | Notes |
| --- | --- | --- | --- |
| `type` | yes | one of the `type:` values above | Must match the folder |
| `status` | yes, except `log` | see the status table | |
| `decided` | decisions | `YYYY-MM-DD` | The date the decision was made |
| `closed` | closed threads | `YYYY-MM-DD` | The date the thread was closed |
| `date` | logs | `YYYY-MM-DD` | Must equal the filename |
| `tickets` | when relevant | `[ACME-1234, ACME-5678]` | Every ticket the note concerns |
| `superseded_by` | superseded decisions | the superseding note's name | See "Superseding" below |
| `supersedes` | superseding decisions | the superseded note's name | |

### Fields written FOR you

**Do not write these by hand.** The `vault-maintain` SessionEnd hook derives them from content and rewrites them on every run, so a hand-written value is overwritten.

| Field | Derived from |
| --- | --- |
| `project` | the workspace's `.vault-config.json` |
| `topics` | matching the note's text against the topic vocabulary |
| `tags` | `project` + `type` + one `topic/<name>` per topic |

You may write `topics:` explicitly when the derived guess would be wrong — a hand-written list is respected and not overwritten. Everything else in that table is regenerated regardless.

### Fields you must NOT write — deprecated counts

Some notes migrated before this contract existed carry cached counts: `open_count`, `done_count`, `days`, `entries`, `decisions`, `threads_open`, `open_items`, `log_days`. **Nothing maintains them** — tick one checkbox and `open_count` is a lie. Never add or update one; remove them when you rewrite a note. If you need a count, derive it at the moment you need it.

### Anything else you find

The tables above are the complete contract. Do not invent fields, and do not copy an unfamiliar one forward because a neighbouring note has it.

### Status values

These are the only legal values. A value outside this list lands the note in no index and matches no query.

| `status` | Use on | Means |
| --- | --- | --- |
| `active` | decision, convention, thread, playbook | In force / being worked |
| `superseded` | decision | Replaced — no longer true |
| `open` | thread | Has unfinished items, not currently being worked |
| `done` | thread, playbook | Everything finished |
| `shipped` | ticket | Merged and released — the terminal state of a healthy ticket note, which is kept, not deleted |
| `reference` | note, research, playbook | Durable material, no lifecycle (a playbook you re-run, like a setup guide) |
| `paused` | overview, thread | Deliberately stopped |
| `trial` | meta | An experiment being evaluated, not yet adopted |

---

## Closing a thread

A thread exists for unfinished work, so a finished thread must not keep reading like one. **Close it** when its last item is ticked, or when the user says it is done or abandoned:

1. **Move out what lasts** — each to the note type that owns it:

   | Found in the thread | Goes to |
   | --- | --- |
   | A decision made along the way | A note in `Decisions/` (if one does not already exist) |
   | A technique, gotcha or fact worth citing later | `Notes/` — or `Research/` if it took investigation |
   | Items still open but no longer part of this thread | Another open thread, or `Overview.md`'s `## Next up` — **ask** before dropping one |
   | What the thread achieved | One clause in today's log `Did` |

2. **Reduce the thread to a closing stub.** Replace the body with the template below and set `status: done` and `closed: YYYY-MM-DD`. The item lists go; git keeps them. The stub stays so links from old logs still resolve.

   ```markdown
   # <Thread name>

   **Goal:** <the original one-line goal>

   **Outcome:** <one line — shipped, or abandoned and why>

   **Moved to:** [[<DecisionNote>]], [[<NoteOrResearch>]], [[<OtherThread>]]
   ```

3. **Remove it from current state.** Take it out of `## Next up`, and repoint or remove links to it from the Overview and from open threads and playbooks.

The lint reports an `unclosed-thread` for a `done` thread that still holds its item lists, and for an open thread whose items are all ticked.

A **playbook** is not closed this way: a `done` playbook keeps its steps, because the steps are the record of how the work was carried out.

---

## Superseding a decision

When a new decision replaces an old one, **edit the old note** — do not simply add a newer one, or both will read as current.

On the old note:

```yaml
status: superseded
superseded_by: <name of the new note>
```

and immediately under its heading:

```markdown
> [!warning] Superseded — replaced by [[<new note>]]
> <One sentence on what changed and why.>
```

On the new note: `supersedes: <name of the old note>`, and a matching `> [!note]` callout.

Then **repoint every current-state note** that linked the old decision to the new one. A superseded decision is linked only from its successor and from logs.

Only record a supersession you can evidence. A wrong one is worse than none.

### When the superseded note does not exist

The user says "this replaces our old decision that X", but no note records X. **Do not fabricate a note to supersede, and do not silently drop the claim.**

1. Search before concluding it is missing — `Decisions/`, then the logs, then the threads.
2. If it genuinely is not there, write the new decision **without** `supersedes:`, and state the replacement in its body: *"Replaces the unrecorded practice that X."*
3. Tell the user in one line that the link is prose rather than frontmatter.

---

## The two-altitude log

`ProgressLog.md` in the root is an **index**: one line per working day, newest first.

```markdown
- **[[Takeoffs/Log/2026-08-19|2026-08-19]]** — ACME-1656 billing joins landed
```

The detail lives in `Log/2026-08-19.md`: **one** `Did` / `Decided` / `Learned` block for the whole day. A second close-out on the same day **merges into those sections** — it never adds a second block, a `###` sub-entry, or a correction of an earlier line. If something said earlier that day is now wrong, fix the line.

---

## What the hook does after you write

The `vault-maintain` SessionEnd hook runs before the vault is committed. It:

1. Fills in `project`, `topics` and `tags` on any note missing them.
2. Regenerates `TopicIndex.md`, `TicketsIndex.md`, `ThreadsIndex.md` and `DecisionsIndex.md`.

It never deletes a file, never moves a file, and never edits a note body.

It also has a **lint mode** that reports, without fixing, every note that breaks this contract: over-budget notes, stray root files, pre-2.0 names, threads that are finished but not closed, `Next:` lines or stacked blocks in logs, links to superseded decisions or finished threads from current-state notes, broken links, links to an index where a specific note belongs, names that are not PascalCase (vault-wide, workspace folders included), missing required sections, and hard-wrapped prose. `condense-vault` runs it and fixes what it finds.

```bash
dev-workbook lint            # or: python3 "<plugin root>/bin/dev-workbook" lint
```

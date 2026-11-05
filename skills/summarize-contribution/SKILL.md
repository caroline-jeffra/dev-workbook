---
name: summarize-contribution
description: Writes or updates a career-facing summary of the user's contribution to a project, stored one-file-per-project in the vault's top-level Contributions folder. Evidence comes from git history, the project's vault workspace, and any tracker the user has CLI access to. Use when the user says "summarize my contribution", "write a CV summary for this project", "update my contribution summary", "what should I put on my CV for this", "what did I accomplish on this project", or when a project is wrapping up, going on pause, or a review/CV/LinkedIn update is due. Not for status or next-work questions — "where did we leave off", "what's the status", "what have I been working on" belong to manage-project-workspaces; this skill is only for career-facing write-ups.
---

# Summarizing a contribution

Produce one durable, career-facing document per project describing what the user did, why it was
hard, and what it demonstrates — written so it can be lifted into a CV, a LinkedIn update, a 360
review, or a blog-post outline without being rewritten each time.

**Vault location:** resolve in this order — (1) the `DEVWB_VAULT` environment variable (or the pre-3.0 `OBSIDIAN_VAULT`), (2) the config file `${XDG_CONFIG_HOME:-~/.config}/dev-workbook/vault` (or the pre-3.0 `…/claudesidion/vault`), (3) the legacy config file `~/.claude/obsidian-vault`, (4) the default `~/ObsidianVault`. A config file holds one line, the vault's path (whitespace trimmed, a leading `~/` or `$HOME/` expanded); `dev-workbook vault-path` prints the result. If none of them yields an existing directory, ask the user where their vault is and write the answer to `~/.config/dev-workbook/vault` (creating the folder) so every future session and hook finds it. Use the resolved absolute path (written below as `$DEVWB_VAULT`) for every read/write.

You normally run this while the working directory is *the project's repo*, not the vault. Address the
vault by absolute path; derive the project from the working directory.

## Where summaries live

**One file per project**, all in a single top-level folder:

```
$DEVWB_VAULT/Contributions/<project>.md
```

- `<project>` is the workspace folder name from `Projects/WorkspaceIndex.md` — so `Contributions/Portal.md`
  pairs with `Projects/Portal/`. Matching names keep `[[wikilinks]]` resolving in both directions.
- Create `Contributions/` if it is missing. Do **not** nest by year, employer, or status — one flat
  folder, one file per project, updated in place over the project's whole life.
- Never create a second file for the same project (no `Portal 2026.md`, no `Portal Q3.md`). A new
  period is an **update to the existing file**, not a new file. See "Updating".
- If a legacy per-period summary already exists inside a workspace folder (e.g.
  `Projects/Portal/CV Summary May-Aug 2026.md`), fold its content into `Contributions/<project>.md`,
  then leave the original in place with a link at the top pointing at the new home. Tell the user;
  do not delete their note yourself.

## Principles

- **Evidence, not recollection.** Every claim traces to a commit, a ticket, a vault note, or
  something the user told you in this session. If you cannot source it, leave it out.
- **Generic skill capture.** Record the full range of what the work demonstrates — architecture,
  data modelling, migration strategy, debugging, security, infrastructure, product judgement,
  collaboration, mentoring, communication, incident response, whatever the evidence shows. Do **not**
  pre-filter toward one target role. The reader decides what to emphasise later; this document's job
  is to have captured it. If the user asks for a specific slant, apply it to the framing, never by
  omitting real work.
- **Don't inflate.** Migration, deletion, and maintenance are credentials in their own right. If the
  history shows mostly upkeep, say so plainly — that is more useful than a document the user cannot
  defend in an interview.
- **Stack is implementation detail.** Name technologies where they carry the difficulty; lead with
  the engineering problem, not the framework.
- **Publishable by default.** This document is written to be pasted into a CV, a LinkedIn post or
  a review form. Assume every line will be read by someone outside the company, and write it that
  way from the start — see "Confidentiality".
- **Integrate on update, never staple.** See "Updating" — this is the rule most likely to be broken.

## Confidentiality

This skill reads from trackers, chat exports, monitoring and internal repos, and writes the result
into the user's markdown vault. The vault is normally a **private** repository, so the risk is not
that the file itself is exposed — it is that the file's whole purpose is to be **quoted outside the
company**, in a CV, a LinkedIn post or an application.

That makes the filtering job different from ordinary secret-handling. Identifiable detail is
genuinely useful in the vault: it is what makes the document a reliable record the user can mine
years later. The rule is therefore not "never record it" but **mark what cannot travel, so the
user never pastes it outward by accident**.

- **Vault copy** — may contain identifiable detail: client names, ticket keys, brands, figures.
- **Anything quoted outward** — must be generalised first.

Keep the two separable *inside the file*, so the split survives without the user remembering it:
write the prose in publishable form, and put anything that must not travel in the marked
`Confidential context` section described below.

If the user's vault is a **public or shared** repository, this changes: treat the file itself as
published and apply the list below to the whole document, `Confidential context` included. Ask if
you cannot tell.

**Never put in the publishable prose:**

- Customer, client or partner names, and anything that identifies them indirectly ("the largest
  German insurer we onboarded"). Use a category: "an enterprise insurance client".
- Named colleagues. Describe the collaboration, not the person: "paired with the platform team",
  not a name. A 360 review is the exception — see below.
- Internal hostnames, URLs, service names not public, repository paths, infrastructure topology,
  account IDs, and anything resembling a credential or token.
- Absolute commercial figures — revenue, contract values, margins, headcount costs — and absolute
  user or transaction counts, unless the company has published them.
- Security specifics that remain exploitable: the vulnerability class and that it was fixed are
  fine, the mechanism and the window of exposure are not.
- Unannounced products, roadmap, reorganisations, or anything under embargo.
- Verbatim internal text — Slack messages, ticket bodies, incident write-ups, review comments.
  Summarise in your own words.

**Write instead:**

| Instead of | Write |
| --- | --- |
| "cut AcmeCorp's invoice run from 40min to 90s" | "cut a major client's invoice run by ~96%" |
| "$2.4M ARR pipeline" | "a pipeline carrying a significant share of new revenue" |
| "fixed the IDOR on /api/v2/accounts" | "found and fixed an access-control flaw in a core API" |
| "Sarah asked me to take over billing" | "took over the billing service at the team's request" |

Relative and proportional figures survive this filter almost always, and are more persuasive than
absolutes: percentages, factors, before/after ratios, "reduced by two thirds". Prefer them anyway.

**Jira and ticket keys** identify the tracker and the project, and mean nothing to an outside
reader. Keep them in the `tickets:` frontmatter and in `Confidential context`, where they stay
useful for a later update — and out of the publishable prose, where they only leak context.

**When the material is essential but not publishable**, do not silently drop it — that loses the
achievement. Record the publishable version in the prose and note what was withheld in a private
`Confidential context` section at the very bottom of the file, under an HTML comment:

```markdown
<!-- Confidential — internal reference only. Do not paste into a CV, post or review form. -->
## Confidential context
- Client: <name>. Contract value <figure>. Withheld from the summary above.
```

That keeps the fact recoverable for the user's own memory while marking clearly that it must not
travel. Say in the run report that the section exists.

**If the user's employment contract or NDA is stricter than this list, it wins.** Where the
publishable framing of an effort is genuinely unclear, ask rather than guessing — one question is
cheaper than an unpublishable document or a leak.

**360 reviews are the one exception on names.** A review names colleagues by necessity. If the user
says the target is a 360 review, names of internal colleagues are allowed in the story seeds and
detail sections — but everything else on the list above still applies, and the file should carry
`audience: internal` in its frontmatter so a later update does not treat it as CV-ready.

## Workflow

Copy this checklist and track progress:

```
Contribution summary progress:
- [ ] Step 1: Locate the project and its existing summary
- [ ] Step 2: Establish identity and date range from git
- [ ] Step 3: Gather git evidence
- [ ] Step 4: Read the vault workspace for domain context
- [ ] Step 5: Ask the user for other evidence sources
- [ ] Step 6: Identify the major efforts
- [ ] Step 7: Write or update the document (updates: state the plan before writing)
- [ ] Step 8: Report the run
```

### Step 1 — Locate the project and its existing summary

1. Get the repo root (`git rev-parse --show-toplevel`, falling back to cwd) and read
   `$DEVWB_VAULT/Projects/WorkspaceIndex.md` (`Projects/_index.md` in a vault from before 2.0) to find the workspace folder. Rows hold paths relative to the machine's code root (`CODE_ROOT`, else `~/.claude/code-root`, else `~/code`); a row starting with `/` is absolute. That
   folder's name is `<project>`.

   **If there is no row**, the project has no workspace. `<project>` is then undefined, and guessing
   it wrong creates the one thing this skill forbids — a second file for a project that already has
   one. So:

   - First check whether a summary already exists under a different name:
     `ls "$DEVWB_VAULT/Contributions/"` and look for anything matching this repo. If one does,
     use that filename and say which one you matched.
   - Otherwise **ask the user what to call it**, proposing the repo directory basename as the
     default. One question, with a default, is cheaper than an unrecoverable duplicate.
   - Note in the run report that domain context will be thin without a workspace, and offer
     `manage-project-workspaces` / `ingest-project-docs`.
2. Check whether `$DEVWB_VAULT/Contributions/<project>.md` exists.
   - **Exists** → this is an **update**. Read it in full before gathering anything. What is already
     recorded determines what new evidence actually matters.
   - **Missing** → this is a **create**.

### Step 2 — Establish identity and date range from git

Do not trust the user's memory of when they worked on something; report back if the git record
differs from what they said. Commands are in [reference/git-evidence.md](reference/git-evidence.md).

- Find every name/email the user committed under — people commit under more than one identity, and
  web-UI merge commits often carry a different display name than local ones. Confirm ambiguous
  identities with the user rather than guessing.
- Derive the true first and last commit dates for those identities. On an update, the range of
  interest starts at the last date the existing document covers.

### Step 3 — Gather git evidence

Using the confirmed identities (see [reference/git-evidence.md](reference/git-evidence.md)):

- Non-merge commits authored by the user, with dates and messages.
- Commit count and insertion/deletion volume — scale, stated as an order of magnitude, not a boast.
- Ticket/issue keys referenced in messages and branch names.
- Branch names. Slugs frequently describe the work better than the commit messages do.
- **Separate authored from shipped.** Merge commits into the mainline are approved PRs/MRs — review
  and integration labour, distinct from authorship. The user's own merges into their feature branches
  are integration work. Both count; they are different claims and must not be blurred.
- Note the larger efforts and epic branches the user participated in, reviewed, or integrated
  against, and be explicit that not all work inside them was theirs.

**Two vocabularies, deliberately.** `reference/git-evidence.md` classifies what git *shows* —
**Authored** / **Shipped** / **Integrated**. The document records what the user can *claim* per
effort — **Owned** / **Contributed to** / **Reviewed and integrated**. They are not the same axis,
so map rather than substitute:

| Git evidence | Effort marker |
|---|---|
| Most non-merge commits in the effort are theirs | **Owned** |
| Some authored commits, others authored the rest | **Contributed to** |
| Few or no authored commits, but merges into mainline and integration merges | **Reviewed and integrated** |
| Authored the design/schema, but the decision was shared | **Contributed to** — and say what was theirs in the effort body |

When authorship and shipping disagree, the body text carries the nuance: "owned the backend
contract; reviewed the frontend" is more accurate than either marker alone.

### Step 4 — Read the vault workspace for domain context

Read `Projects/<project>/` — `Overview.md`, the progress log, decisions/ADRs, and open threads
(structured workspaces use indexes and one-note-per-fact; see `manage-project-workspaces`). This is
where the *why* lives: what the software is for, what the commercial or operational stakes are, and
which decisions were contested. Git shows what changed; the workspace shows what it was worth.

### Step 5 — Ask the user for other evidence sources

Git and the vault miss the things that matter most to a review or a CV: outcomes, adoption, incidents
handled, and how the user worked with people. **Ask** — do not skip this and do not invent it.

Detect what is available first (`gh`, `glab`, `acli`, and any project-specific CLI or MCP server this
session can reach), then ask a single consolidated question offering what you found, plus an open
option. Suggested sources:

- **Trackers** — `acli` for Jira, `gh issue` / `gh pr` for GitHub, `glab` for GitLab. Useful for
  ticket titles and epic names that give commit keys meaning, and for review load (PRs reviewed, not
  just authored).
- **Anything else with CLI or MCP access** in this session — a docs store, a Slack export, an
  analytics or monitoring tool.
- **The user directly** — impact and outcomes git cannot show: what the work enabled, numbers that
  moved, incidents averted, feedback received, people mentored, decisions they drove or lost.

Use whatever they offer; record in the run report which sources were unavailable rather than
silently skipping them. If they decline, proceed on git and vault alone and say so.

These sources are where confidential material enters — client names, figures, verbatim internal
text. Apply "Confidentiality" as you take notes, not after the document is drafted.

### Step 6 — Identify the major efforts

**This section is required in the output; do not ship a summary without it.**

A major effort is a coherent, named body of work spanning multiple commits and usually multiple
tickets or weeks — a migration, a new subsystem, a hardening pass, an upgrade ladder, an incident and
its follow-through. Recover them by clustering the evidence: epic branches, ticket prefixes, branch
slug families, and progress-log arcs.

Aim for **three to seven**. Fewer and the document says nothing; more and every effort is really a
task. Fold the leftovers into the "Other work" section rather than promoting them.

For each effort, establish four things — this is the shape it is written in:

- **Problem** — what was wrong or needed, and why it mattered to someone other than the author.
- **What I did** — the actual work, concretely.
- **Judgement calls** — the decisions with a defensible alternative. This is the part an interviewer
  or reviewer actually probes, and the part nothing else in the vault captures.
- **Outcome** — what shipped and what changed. If it is unfinished or was abandoned, say that; an
  honest partial outcome is usable, a vague one is not.

Mark efforts the user **contributed to or reviewed** rather than owned, explicitly and per effort.
Overstated ownership is the single most damaging error this document can contain.

### Step 7 — Write or update the document

Before writing, re-read your drafted prose once against "Confidentiality" — client names, named
colleagues, absolute figures, internal hostnames, verbatim internal text. Anything on that list
either gets generalised in place or moves to the `Confidential context` section; what it must not
do is sit unmarked in prose the user will later paste into an application.

In a background session (`CLAUDE_JOB_DIR` is set) run `dev-workbook stage "Contributions/<project>.md"` first and read and write the path it prints instead; the session-end hook merges it into the vault.

Write to `$DEVWB_VAULT/Contributions/<project>.md` using the structure in
[reference/template.md](reference/template.md): light frontmatter, then **Context → Major efforts →
At a glance → Detail by theme → Signals → Story seeds → Timeline → Related notes**.

Per-section guidance, including what each of the four target usages (CV, LinkedIn, 360 review, blog
topics) draws from, is in [reference/template.md](reference/template.md). Read it before writing.

#### Creating

**On the `role` frontmatter field:** fill it only where the evidence settles it — a single-author
repo with no other committers is `sole author`; someone who set standards, owned the pipeline and
accepted others' merges over a long period is a lead. Where the evidence does not settle it,
**omit the field** rather than inventing a title. Do not ask for it as a separate question; if the
user volunteers their title in Step 5, use it. The role is conveyed by the At a glance bullets
regardless, so an absent field costs the document nothing while a wrong one is a claim the user
cannot defend.

Write all sections. Where evidence for a section is genuinely absent, keep the heading and write one
line naming what is missing (e.g. "No outcome data yet — ask after the next release") rather than
deleting the heading or padding it. The gap is information, and it tells the next update what to
collect.

#### Updating

**An update rewrites; it does not append.** The document must read as though written today, in one
sitting, by someone who knew the whole story. A reader must not be able to tell where one update
ended and the next began.

For each section:

- **Context** — revise only if the project's purpose or stakes actually changed. Usually untouched.
- **Major efforts** — the heart of the update.
  - New effort → a new subsection, written in the same four-field shape.
  - Continuing effort → **revise its four fields in place**. A migration that was "in progress" and
    is now finished gets a rewritten Outcome, not a second paragraph beneath the first. Judgement
    calls that proved right or wrong get updated with what actually happened.
  - Completed effort → keep it, in past tense. Prune only if it has shrunk into a task, in which
    case demote it to "Other work" rather than deleting it.
  - Re-check the three-to-seven range after adding. If it has grown past seven, the right fix is
    almost always merging two efforts that turned out to be one, not deleting the smallest.
- **At a glance** — rewrite from scratch against the whole project, not just the new period. Two
  bullets describing four months and eight describing sixteen is a worse document, not a fuller one.
- **Detail by theme** — merge new items into existing themes; create a theme only for genuinely new
  ground. Rewrite bullets that the new work has superseded — if the summary says a system was built
  and it has since been replaced, that is one bullet about its life, not two contradicting each other.
- **Signals** — merge; keep the strongest evidence per claim rather than accumulating every instance.
- **Story seeds** — drop seeds already written up or gone stale; add what the new period surfaced.
- **Timeline** — **the only append-only section.** Add one dated line per update.
- **Frontmatter** — extend `period` to the new end date, and merge `efforts`, `skills` and `tickets`.

#### The pre-write pass (updates only)

**Before writing anything, re-read the whole document and write out an explicit plan** — a short
list, in your reply, of what you intend to do to each part:

```
Update plan:
- Context — unchanged
- Effort "SPA migration" — REVISE Outcome (was in-progress, now shipped) and Judgement calls
- Effort "Permissions hardening" — unchanged
- NEW effort "Incident response — Aug outage"
- At a glance — REWRITE all bullets against the whole project
- Detail by theme / CI-CD — MERGE two new items; REWRITE the bullet about the old test harness
  (superseded by the new one)
- Signals — MERGE collaboration evidence, drop the weaker instance
- Story seeds — DROP "enum migration" (written up), ADD "timezone correctness"
- Timeline — APPEND one line
```

Every existing section must appear in the plan as **REVISE**, **REWRITE**, **MERGE**, **DROP** or
**unchanged**. If the only verbs in your plan are ADD and APPEND, you are stapling — go back and
find what the new work actually supersedes, because new work almost always changes the standing of
old work. Then cut what has become redundant and write the document.

The document should get **sharper** as the project goes on, not merely longer.

### Step 8 — Report the run

Tell the user, briefly:

- Which file was written, and whether it was a create or an update.
- The date range git actually shows, called out if it differs from what they said.
- The major efforts recorded, and which are marked as review/collaboration rather than owned.
- Evidence sources used, and any that were unavailable or declined.
- What you could not source — the specific gaps worth filling before this is used for a review or an
  application.
- Anything withheld for confidentiality, and whether a `Confidential context` section was added.

## Related skills

- `manage-project-workspaces` — the per-repo workspace this reads for domain context.
- `ingest-project-docs` — bootstrap a workspace first if the project has none.
- `condense-vault` — explicitly excludes `Contributions/` from its stale-content sweep. These
  documents are meant to sit untouched between updates; do not let a cleanup run condense them.

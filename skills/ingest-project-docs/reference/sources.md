# Ingestion sources & mapping

## Contents
- GitHub commands (gh)
- GitLab commands (glab)
- In-repo docs & temp files
- Source → workspace mapping
- Ingestion log template

All CLI commands run from the repo's working directory. Assume the relevant CLI is authenticated for
that repo; on a `401`/auth error, record it in the run report and continue with other sources.

## GitHub commands (gh)

```bash
# Open issues (title, number, url, labels, one-line body)
gh issue list --state open --limit 200 \
  --json number,title,url,labels,milestone,body

# Open milestones
gh api "repos/{owner}/{repo}/milestones?state=open" \
  --jq '.[] | {title, description, due_on, html_url}'

# Open PRs
gh pr list --state open --limit 200 \
  --json number,title,url,labels,isDraft,body
```

Keep only title, number, url, labels, milestone, and a one-line gist derived from `body`. Do not copy
full bodies into the vault.

## GitLab commands (glab)

```bash
# Open issues
glab issue list --output json --per-page 200

# Open issues under a milestone
glab issue list --milestone "<name>" --output json --per-page 200

# Open merge requests
glab mr list --output json --per-page 200

# Milestones (no first-class list subcommand — use the API)
glab api "projects/:id/milestones?state=active"
```

`:id` resolves to the current project. Same rule: summarize, link via each item's `web_url`.

## In-repo docs & temp files

```bash
# Tracked docs
ls README* 2>/dev/null; find docs -maxdepth 2 -name '*.md' 2>/dev/null
ls CLAUDE.md AGENTS.md GEMINI.md .github/copilot-instructions.md 2>/dev/null
find .claude .cursor/rules -maxdepth 2 -type f 2>/dev/null
find . -maxdepth 2 -iregex '.*\(architecture\|adr\).*\.md' 2>/dev/null

# Temp / scratch / untracked / ignored working files
git status --porcelain --ignored | grep -E '^(\?\?|!!)'
ls TODO.md NOTES.md SCRATCH* 2>/dev/null
```

Read each doc; summarize its purpose in 1–3 bullets. For temp files, extract actionable TODOs and any
"why" context — these are often the richest undocumented source. Link docs by repo-relative path.

## Source → workspace mapping

Append/merge into the structured workspace; never overwrite. Dedupe on the key shown. Formats follow the templates in [manage-project-workspaces/reference/templates.md](../../manage-project-workspaces/reference/templates.md), one file per type.

| Source | Lands in | Form | Dedupe key |
|---|---|---|---|
| README intro | `Overview.md` | "What this is" — two or three sentences | — |
| Issue/PR tracker URLs | `Overview.md` | Trackers section | url |
| docs/, agent instruction files (CLAUDE.md, AGENTS.md, GEMINI.md, .cursor/rules, copilot-instructions.md, .claude/) | `Overview.md` or `Research/<Subject>Reference.md` | One bullet each in the Overview, linked by repo path; a doc worth summarising gets its own research note | file path |
| Open issues | `Threads/<NounPhrase>.md` | `- [ ] issue <n>: <title> ([link](url))` under `## Open`, grouped by theme into one thread — never a bare `#<n>`, which viewers read as a tag | issue number |
| TODOs in temp files | `Threads/<NounPhrase>.md` | `- [ ] <action> (from <file>)` | action text |
| Open PRs/MRs | `Threads/<NounPhrase>.md` | `- [ ] PR/MR !<n> <title> ([link](url))` | pr/mr number |
| Runbooks, setup or upgrade guides | `Playbooks/<Area><Subject>.md` | Playbook template, `status: reference` | file path |
| Milestones | `Overview.md` | `## Next up` bullets: title, due date, link | milestone title |
| graphify report (`graphify-out/GRAPH_REPORT.md`), when present | `Research/ArchitectureMap.md` | TL;DR, then one bullet per real area: its key files and god nodes; link `graphify-out/graph.html` by repo path | — (rewrite in place) |
| Diagram files (`*.excalidraw`, `*.excalidraw.md`, `*.mmd`), when present | `Diagrams/<Area><Subject>.md` (or `.excalidraw.md` when the vault has the plugin) | Diagram template; Mermaid summarising the labels and arrows, linked back | file path |
| Decisions in docs/ADRs | `Decisions/<Claim>.md` | One decision note each | decision title |
| The ingestion run itself | `Log/YYYY-MM-DD.md` + `ProgressLog.md` line | Log template (below) | date |

## Ingestion log template

`Log/YYYY-MM-DD.md` — merge into the day's note if it already exists. No `Next:` line; what to pick up first goes in `Overview.md`'s `## Next up`.

```markdown
---
type: log
date: YYYY-MM-DD
---

# YYYY-MM-DD

- **Did:** Bootstrapped the workspace from existing sources — <N> open issues, <N> milestones, <N> open PRs/MRs, README + <N> docs, <N> temp files.
- **Learned:** <sources that failed or were empty, with the reason; omit if none>
- **Links:** [[<thread>]], [[<thread>]]
```

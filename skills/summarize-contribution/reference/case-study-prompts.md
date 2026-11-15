---
type: case-study-prompts
---

# Case study prompts

The questions performance reviews and interviews ask for a specific example of. `manage-project-workspaces` flags work against this list when it logs a session; `summarize-contribution` turns the flags into stories. **Edit freely** — add a prompt you were actually asked, drop one that never comes up. Keep the slug short, kebab-case and stable: logs and summaries tag stories with it.

**Want** says which stories to collect: `pair` means flag a success *and* a failure, because interviewers often ask for both; `failure` means the prompt is a failure story by nature; `any` means one good story is enough.

**Commits** says how visible the story is in git. A `low` story mostly lives in review threads, ticket comments, design docs and conversation, so it has to be caught when it happens or asked about later.

| Slug | Prompt | Want | Commits | What it tends to look like |
| --- | --- | --- | --- | --- |
| `end-to-end-feature` | A feature you owned end to end, starting from a vague goal | pair | high | An epic or design doc you wrote yourself; a run of PRs from scaffolding to launch; spec revisions along the way; a feature flag you later removed |
| `legacy-migration` | Working in or migrating legacy code | any | high | Changes to old, rarely touched files; tests added before refactoring; adapter or dual-write layers; deprecation notices and removal PRs |
| `performance-diagnosis` | A performance problem you diagnosed, ideally in a database | any | high | Index additions, query rewrites, N+1 fixes; EXPLAIN output pasted into PRs or tickets; before/after latency numbers |
| `production-incident` | A production incident you were part of | any | medium | Postmortems or incident docs that name you; hotfixes merged outside normal hours; links to incident channels in tickets |
| `trade-off` | A trade-off where you chose "good enough", or pushed for more care | pair | medium | TODOs linked to follow-up tickets; PR descriptions explaining what was left out; or review comments asking for tests and edge cases, and PRs held back |
| `ai-tools` | Using AI tools: a time it helped a lot, and a time it was wrong | pair | medium | AI co-author trailers or tool mentions in PRs; large boilerplate PRs that landed fast; reviews or reverts catching generated code that was wrong (made-up APIs, subtle logic errors) |
| `detective-bug` | A bug that took real detective work to find (not performance) | any | medium | A ticket open a long time that ends in a small diff; "root cause" in the PR description; race conditions, caching, timezones, flaky tests |
| `owned-mistake` | A mistake you made, and how you owned it | failure | medium | Reverts or hotfixes after your own PR; follow-up tickets that reference your change |
| `technical-disagreement` | A technical disagreement with a teammate or lead, and how it was resolved | pair | low | Long review threads, design docs with lots of comments, competing PRs, an approach you argued against that shipped anyway |
| `scope-pushback` | Pushing back on a requirement or renegotiating scope | pair | low | Ticket descriptions rewritten mid-flight, "phase 2" or descoped tickets, comments proposing alternatives |
| `influence-adoption` | Getting a team to adopt a practice or tool without being in charge | pair | medium | New lint rules, shared libraries, PR templates, RFCs, the same change landed across many repos |
| `mentoring` | Mentoring, onboarding or unblocking someone | any | low | Heavy review activity on others' PRs, co-authored commits, onboarding docs |
| `fast-ramp-up` | Ramping up fast on an unfamiliar language, codebase or domain | any | medium | First commits in a new repo or stack; early PRs with many review rounds that drop off over time |
| `developer-experience` | Improving developer experience (CI, build times, test reliability, local setup) | any | high | Pipeline configs, Dockerfiles, test infrastructure; before/after timings |
| `observability` | Making a system easier to observe (logging, metrics, alerting) | any | high | New dashboards, monitors, tracing or structured logs, often right after an incident |
| `hindsight-design` | A design decision you'd make differently with hindsight | failure | medium | APIs or schemas you introduced that you or others later reworked |
| `cross-team` | Working across team boundaries or with an external service | any | medium | Commits in other teams' repos, API clients, webhooks, contract tests, vendor support tickets |
| `security-integrity` | A security, privacy or data-integrity problem you caught or fixed | any | high | Auth or permission changes, input validation, CVE dependency bumps, data repair scripts |
| `cancelled-project` | A project that was cancelled, failed, or didn't land as hoped | failure | low | PRs closed without merging, abandoned branches, "Won't Do" tickets, features rolled back |
| `unasked-fix` | Fixing a problem nobody asked you to | any | medium | Tickets you filed yourself, PRs with no linked ticket, small cleanups that grew |
| `hard-deadline` | Delivering under a hard deadline or after priorities shifted | pair | medium | Bursts of commits before release dates, partial launches behind feature flags, reordered epics |

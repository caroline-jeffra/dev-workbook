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

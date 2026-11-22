## TimeTracking.md — optional, on request only

A summary table and nothing else: every number links to where its detail lives. Created only when the user asks for time tracking; the method and the script behind the numbers are in [time-tracking.md](../time-tracking.md).

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

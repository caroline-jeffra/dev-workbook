# Time tracking

Optional, per workspace: hours actually spent per phase, against the estimates the plan made. **Create it only when the user asks** — "set up time tracking", "track my hours on this", "how long has phase 2 taken". Never scaffold it by default.

## Setting it up

Some projects track hours per phase against their estimates. It is **opt-in per workspace**: set it up only when the user asks ("set up time tracking", "track my hours on this project"). Never create `TimeTracking.md` unprompted, and never suggest it as part of an ordinary logging pass.

To set it up: create `TimeTracking.md` from the template in [templates/time-tracking.md](templates/time-tracking.md), with one row per phase (and subphase, where the plan estimates one) taken from the project's playbooks. Then measure the time already spent, as far back as the transcripts go, with the method below. Tell the user how far back that reached: transcripts expire after 30 days by default, so anything earlier can only come from the user's own records.

Once the file exists, every close-out updates it (the update line is in [closeout.md](closeout.md)).

## The file

`TimeTracking.md` in the workspace root, from the template in [templates/time-tracking.md](templates/time-tracking.md). It is **a summary table and nothing else**:

- **Phases table** — one bold row per phase, plain subphase rows beneath; columns Phase, Status, Estimate, Actual, Variance, Sittings, Dates, Links.
- **Weekly hours table** — weekday, weekend and total hours per Mon–Sun week, against the weekly budget.
- **One budget line** above them, linking the decision that set the budget.

Everything else is linked, never written here: the plan and estimates live in the phase's playbook, what happened lives in the logs, and any analysis (estimate accuracy, pace, whether the deadline holds) goes in a `Research/` note such as `EstimateAccuracyAnalysis`.

## Measuring

**Source: Claude Code session transcripts**, measured by `dev-workbook hours` (or `python3 "<plugin root>/bin/dev-workbook" hours` when the command is not on PATH):

```bash
dev-workbook hours --repo <repo path> --since <tracked_through + 1 day> --by sitting
dev-workbook hours --repo <repo path> --since <first day of the week> --by week
```

| Rule | Why |
| --- | --- |
| **Only messages the user typed count** | A session left open, or a long autonomous run by the agent, is not time the user spent |
| **A gap over 15 minutes is a break**; the runs between breaks are sittings | Keeps a coffee break inside a sitting and a night's sleep outside it |
| **Sessions are pooled before measuring** | Two sessions open at once must not count twice |
| **A sitting books under the day it started** | Same rule as the TasksArchive; a late session past midnight stays on its day |
| **The result is a floor**, accurate to about ±15% | Thinking away from the keyboard and work without a session open are not counted |

**Hours come only from the script's output.** Never derive them from a session's start and end times ("21:57 → ~23:30, 1.55 hrs"). A session's clock time counts every pause under an hour as work. One project's log recorded it that way and overstated a week by 55% (7.53 recorded vs 4.87 active). If the script cannot run, leave the row unchanged and say so; do not estimate.

**Weekday means Monday to Friday**, by the date the sitting started; Saturday and Sunday are weekend. Take the split from `--by week` rather than adding days up by hand. A Friday once landed in the weekend column that way.

Keep the 15-minute threshold fixed. If it ever changes, every historical figure has to be re-measured, so say so in the budget decision.

**Cross-checks**, weaker than transcripts:

- **Commit timings** (`git log --since … --until … --format='%ad %s' --date=iso`): which phase task a sitting worked on.
- **The day's log**: what the sitting achieved.

## Transcripts expire — update incrementally

Claude Code deletes transcripts after `cleanupPeriodDays` (30 by default), so **past hours cannot be re-measured later**. The table is the durable record, and `tracked_through:` marks how far it goes.

- **Update at every close-out** while the file exists, alongside the log: measure from the day after `tracked_through:`, attribute each sitting, update the rows, and move `tracked_through:` forward.
- **Never recompute a closed week or a `done` phase** from transcripts. The older sessions may already be gone, and a recount would silently lower the figure.
- If the user wants a longer window, suggest raising `cleanupPeriodDays` in `~/.claude/settings.json`.

## Attributing a sitting

Each sitting's hours go to exactly one phase row, and to a subphase row if one exists:

1. Match the sitting to the commits made during it, and to the subphase they name.
2. With no commits, use the day's log and the sitting's first message, which the script prints.
3. Planning and project management (vault upkeep, tracking itself) have their own rows with no estimate. Do not fold them into a phase.
4. If a sitting genuinely spans two subphases, split it by commit times, not evenly.

## Updating the rows

- **Actual** and **Sittings**: add the new sittings to the phase and subphase rows, and to **Total**.
- **Status**: `planned` → `active` on the first sitting, and `done` when the phase's done-condition is met. A phase that is abandoned is marked `dropped`.
- **Variance**: fill it in when a row becomes `done`, as `(actual − estimate) / estimate`, a signed whole percent.
- **Estimate**: when a plan re-estimates, overwrite the number and record the change in the budget decision. No strike-throughs or footnote marks in the table.
- **Weekly hours**: add or update the current week's row. Close a week once it has passed and leave it alone afterwards.

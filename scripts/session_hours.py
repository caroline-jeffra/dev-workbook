#!/usr/bin/env python3
"""Measure the hours a person actively spent on a repo, from Claude Code session transcripts.

Used by the optional workspace time tracking (skills/manage-project-workspaces/reference/
time-tracking.md). Read-only: it reads transcripts and prints a table.

The method, kept stable so figures stay comparable over time:

  * Only messages the user typed count. Claude's turns, tool results, system reminders and
    compaction summaries are filtered out — a session left open, or a long autonomous run by
    Claude, is not time the user spent.
  * Timestamps from every session are pooled before measuring, so two sessions open at once are
    not counted twice.
  * Active time is the sum of gaps between consecutive user messages, discarding any gap longer
    than the idle threshold (15 minutes) as a break. The runs those breaks separate are
    "sittings".
  * A sitting books under the local date it started, even if it runs past midnight.

The result is a floor on effort: thinking away from the keyboard and work done without a
session open are not counted. Treat figures as accurate to about 15%.

Usage:
    session_hours.py [--repo PATH] [--transcripts DIR ...] [--since YYYY-MM-DD]
                     [--until YYYY-MM-DD] [--idle MINUTES] [--by sitting|day|week]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"


def encode(path: Path) -> str:
    """Claude Code's directory name for a working directory: every non-alphanumeric is '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def transcript_dirs(repo: Path) -> list[Path]:
    """The repo's own transcript folder plus any for its Claude Code worktrees."""
    base = encode(repo.resolve())
    if not PROJECTS.is_dir():
        return []
    return sorted(
        d for d in PROJECTS.iterdir()
        if d.is_dir() and (d.name == base or d.name.startswith(base + "--claude-worktrees-"))
    )


def is_user_typed(o: dict) -> bool:
    """Only messages the user typed: not tool results, reminders, summaries or Claude's turns."""
    if o.get("type") != "user" or o.get("isMeta") or o.get("isCompactSummary"):
        return False
    m = o.get("message")
    if not isinstance(m, dict) or m.get("role") != "user":
        return False
    c = m.get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return False
        text = " ".join(
            b["text"] for b in c
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        )
    else:
        text = c if isinstance(c, str) else ""
    head = text.lstrip()[:200]
    if not head or "system-reminder" in head or head.startswith("<local-command-stdout>"):
        return False
    return True


def first_text(o: dict) -> str:
    m = o.get("message")
    c = m.get("content") if isinstance(m, dict) else None
    if isinstance(c, list):
        c = " ".join(b["text"] for b in c
                     if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str))
    return " ".join(str(c or "").split())


def user_messages(dirs: list[Path]) -> list[tuple[datetime, str]]:
    out: list[tuple[datetime, str]] = []
    for d in dirs:
        for f in sorted(d.glob("*.jsonl")):
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.lstrip().startswith("{"):
                        continue
                    try:
                        o = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (not isinstance(o, dict) or not isinstance(o.get("timestamp"), str)
                            or not is_user_typed(o)):
                        continue
                    try:
                        ts = datetime.fromisoformat(o["timestamp"].replace("Z", "+00:00")).astimezone()
                    except ValueError:
                        continue
                    out.append((ts, first_text(o)))
    out.sort(key=lambda x: x[0])
    return out


def sittings(msgs: list[tuple[datetime, str]], idle: timedelta) -> list[dict]:
    result: list[dict] = []
    for ts, text in msgs:
        if result and ts - result[-1]["end"] <= idle:
            result[-1]["end"] = ts
            result[-1]["messages"] += 1
        else:
            result.append({"start": ts, "end": ts, "messages": 1, "first": text})
    for s in result:
        s["hours"] = (s["end"] - s["start"]).total_seconds() / 3600
        s["day"] = s["start"].date()
    return result


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--transcripts", type=Path, action="append", default=[],
                    help="transcript folder(s) to read instead of deriving them from --repo")
    ap.add_argument("--since", type=date.fromisoformat)
    ap.add_argument("--until", type=date.fromisoformat)
    ap.add_argument("--idle", type=float, default=15.0, help="idle threshold in minutes")
    ap.add_argument("--by", choices=("sitting", "day", "week"), default="sitting")
    a = ap.parse_args(argv)

    dirs = a.transcripts or transcript_dirs(a.repo)
    if not dirs:
        print(f"no transcripts found for {a.repo} under {PROJECTS}", file=sys.stderr)
        return 1

    rows = [
        s for s in sittings(user_messages(dirs), timedelta(minutes=a.idle))
        if (a.since is None or s["day"] >= a.since) and (a.until is None or s["day"] <= a.until)
    ]

    if a.by == "sitting":
        print("| Date | Start | End | Hours | Messages | First message |")
        print("| --- | --- | --- | --- | --- | --- |")
        for s in rows:
            first = s["first"][:70].replace("|", "\\|")
            print(f"| {s['day']} | {s['start']:%H:%M} | {s['end']:%H:%M} | {s['hours']:.2f} "
                  f"| {s['messages']} | {first} |")
    elif a.by == "day":
        print("| Date | Hours | Sittings |")
        print("| --- | --- | --- |")
        days: dict[date, list[dict]] = {}
        for s in rows:
            days.setdefault(s["day"], []).append(s)
        for d, ss in sorted(days.items()):
            print(f"| {d} | {sum(s['hours'] for s in ss):.2f} | {len(ss)} |")
    else:
        print("| Week | Weekday | Weekend | Total |")
        print("| --- | --- | --- | --- |")
        weeks: dict[date, list[float]] = {}
        for s in rows:
            w = weeks.setdefault(week_start(s["day"]), [0.0, 0.0])
            w[1 if s["day"].weekday() >= 5 else 0] += s["hours"]
        for w, (wd, we) in sorted(weeks.items()):
            end = w + timedelta(days=6)
            label = f"{w:%b} {w.day}–{end.day}" if w.month == end.month else f"{w:%b} {w.day}–{end:%b} {end.day}"
            print(f"| {label} | {wd:.2f} | {we:.2f} | {wd + we:.2f} |")

    total = sum(s["hours"] for s in rows)
    print(f"\nTotal: {total:.2f} h across {len(rows)} sitting(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

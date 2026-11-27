#!/usr/bin/env python3
"""Tests for scripts/session_hours.py — the time-tracking measurement.

    python3 tests/test-session-hours.py
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import session_hours as sh  # noqa: E402

PASS = 0
FAIL: list[str] = []


def check(cond: bool, name: str, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print(f"  \033[32mok\033[0m   {name}")
    else:
        FAIL.append(name)
        print(f"  \033[31mFAIL\033[0m {name}")
        if detail:
            print(f"       {detail}")


def at(day: str, hm: str) -> datetime:
    """A local wall-clock time, with the UTC offset in force on that date (not today's)."""
    return datetime.fromisoformat(f"{day}T{hm}:00").astimezone()


def user(ts: datetime, text: str = "go") -> dict:
    return {"type": "user", "timestamp": ts.astimezone(timezone.utc).isoformat(),
            "message": {"role": "user", "content": text}}


def write_session(d: Path, name: str, records: list[dict]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")


def run(args: list[str]) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        sh.main(args)
    return buf.getvalue()


tmp = Path(tempfile.mkdtemp(prefix="dev-workbook-sh-tests."))
try:
    t = tmp / "transcripts"
    day = "2026-10-05"   # a Monday

    print("\n\033[1mOnly typed messages count\033[0m")
    write_session(t, "a", [
        user(at(day, "10:00"), "start"),
        user(at(day, "10:10"), "more"),
        # Claude's turn, a tool result, a reminder and a summary — none is the user present.
        {"type": "assistant", "timestamp": at(day, "10:40").isoformat(),
         "message": {"role": "assistant", "content": "working"}},
        {"type": "user", "timestamp": at(day, "10:41").isoformat(),
         "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}},
        user(at(day, "10:42"), "<system-reminder>ping</system-reminder>"),
        {**user(at(day, "10:43"), "summary"), "isCompactSummary": True},
        user(at(day, "10:20"), "last"),
    ])
    msgs = sh.user_messages([t])
    check(len(msgs) == 3, "tool results, reminders, summaries and Claude's turns are ignored",
          f"got {len(msgs)}")

    print("\n\033[1mIdle gaps split sittings\033[0m")
    s = sh.sittings(msgs, timedelta(minutes=15))
    check(len(s) == 1 and abs(s[0]["hours"] - 20 / 60) < 1e-6,
          "10:00 → 10:20 with 10-minute gaps is one 0.33 h sitting", str(s))

    write_session(t, "b", [user(at(day, "11:00")), user(at(day, "11:30"))])
    s = sh.sittings(sh.user_messages([t]), timedelta(minutes=15))
    check(len(s) == 3, "a 30-minute gap is a break, not work", f"got {len(s)} sittings")

    print("\n\033[1mParallel sessions are not double-counted\033[0m")
    t2 = tmp / "parallel"
    write_session(t2, "x", [user(at(day, "09:00")), user(at(day, "09:10")), user(at(day, "09:20"))])
    write_session(t2, "y", [user(at(day, "09:05")), user(at(day, "09:15"))])
    s = sh.sittings(sh.user_messages([t2]), timedelta(minutes=15))
    check(len(s) == 1 and abs(s[0]["hours"] - 20 / 60) < 1e-6,
          "two sessions open 09:00–09:20 count 0.33 h, not 0.5 h", str(s))

    print("\n\033[1mA sitting books under the day it started\033[0m")
    t3 = tmp / "midnight"
    write_session(t3, "z", [user(at(day, "23:50")), user(at("2026-10-06", "00:05"))])
    out = run(["--transcripts", str(t3), "--by", "day"])
    check("| 2026-10-05 | 0.25 | 1 |" in out and "2026-10-06" not in out,
          "a sitting from 23:50 to 00:05 books 0.25 h on the start date", out)

    print("\n\033[1mWeekly split\033[0m")
    t4 = tmp / "weekly"
    write_session(t4, "w", [
        user(at("2026-10-05", "20:00")), user(at("2026-10-05", "21:00")),     # Mon — gap is a break
        user(at("2026-10-05", "21:10")),
        user(at("2026-10-10", "10:00")), user(at("2026-10-10", "10:12")),     # Sat
    ])
    out = run(["--transcripts", str(t4), "--by", "week"])
    check("| Oct 5–11 | 0.17 | 0.20 | 0.37 |" in out,
          "weekday and weekend hours are split within a Mon–Sun week", out)

    print("\n\033[1m--since / --until\033[0m")
    out = run(["--transcripts", str(t4), "--since", "2026-10-06", "--by", "day"])
    check("2026-10-05" not in out and "2026-10-10" in out, "--since drops earlier days", out)

    print("\n\033[1mRepo → transcript folders\033[0m")
    check(sh.encode(Path("/Users/a/code/garden-planner")) == "-Users-a-code-garden-planner",
          "a repo path encodes the way Claude Code names its folder")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# Records of an unexpected shape are skipped, not fatal.
for weird in ({"type": "user", "message": "str"}, {"type": "user", "timestamp": 5, "message": {"role": "user", "content": "hi"}},
              {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "message": {"role": "user", "content": [{"type": "text", "text": 7}]}}):
    try:
        sh.is_user_typed(weird) and sh.first_text(weird)
        check(True, f"odd record tolerated: {str(weird)[:40]}")
    except Exception as exc:  # noqa: BLE001
        check(False, f"odd record tolerated: {str(weird)[:40]}", repr(exc))

print()
if not FAIL:
    print(f"\033[32m{PASS} passed\033[0m")
    sys.exit(0)
print(f"\033[31m{len(FAIL)} failed\033[0m, {PASS} passed")
for n in FAIL:
    print(f"  - {n}")
sys.exit(1)

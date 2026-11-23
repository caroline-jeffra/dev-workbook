#!/usr/bin/env python3
"""Tests for scripts/workspace_closeout.py — `dev-workbook closeout`, the one-call close-out writer.

Every case builds a temp vault (never the real one); HOME, XDG_CONFIG_HOME, XDG_STATE_HOME,
CODE_ROOT, DEVWB_VAULT, CLAUDE_JOB_DIR and CLAUDE_CODE_SESSION_ID are controlled so the real
machine never leaks in. Run directly:

    python3 tests/test-workspace-closeout.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = str(ROOT / "bin" / "dev-workbook")

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


def section(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")


TMP = Path(tempfile.mkdtemp(prefix="dev-workbook-closeout."))
HOME = TMP / "home"
HOME.mkdir()
for var in ("DEVWB_VAULT", "OBSIDIAN_VAULT", "CODE_ROOT", "CLAUDE_JOB_DIR", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PID"):
    os.environ.pop(var, None)
os.environ.update({"HOME": str(HOME), "XDG_CONFIG_HOME": str(TMP / "xdg"), "XDG_STATE_HOME": str(TMP / "state"),
                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                   "GIT_COMMITTER_EMAIL": "t@t"})

MARKER = "MARKER-7f3a91"
DATE = "2026-11-23"

ARCHIVE = f"""---
created: 2026-08-30
tags: [index, archive]
---

# Tasks Archive

One line per working day, newest year first. This is the quick-reference for personal update meetings.

Rows are deliberately **terse**: one short clause per project touched that day. No links inside table cells.

**Coverage starts 2026-07-10.** Work predating this is covered narratively.

# 2026

## Nov 2026

### Month's Projects
[[Bert/Overview|Bert]], [[Other/Overview|other-thing]]

| Date | Tasks |
| ---- | ----- |
| 22   | story-scraper investigation {MARKER} |
| 20   | Bert thing |
| 3    | **Bert milestone** |

## Oct 2026

### Month's Projects
[[Other/Overview|other-thing]], [[Alpha/Overview|alpha-kebab]]

| Date | Tasks |
| ---- | ----- |
| 30   | a |
| 31   | b |
| 29   | c |

## Sep 2026

### Month's Projects
[[Bert/Overview|Bert]]

| Date | Tasks |
| ---- | ----- |
| 5    | d |
"""
LOG_OLD = f"---\ntype: log\ndate: {DATE}\n---\n\n# {DATE}\n\n- **Did:** built brief\n- **Links:** [[Thread]]\n"
PROGRESS = f"""---
type: log-index
status: reference
---

# Progress log — Alpha

One line per working day. Detail lives in the dated note.

- **[[Alpha/Log/2026-11-20|2026-11-20]]** — twentieth {MARKER}
- **[[Alpha/Log/2026-11-05|2026-11-05]]** — fifth
"""
PAYLOAD = {"date": DATE, "headline": "Shipped the thing", "did": ["built brief", "wrote tests"], "decided": [],
           "learned": [], "case_study": [], "links": [], "archive": "Alpha brief built", "project": None}


def vault(name: str, *, archive: str | None = ARCHIVE, progress: str | None = PROGRESS, log: str | None = None,
          structured: bool = True) -> Path:
    v = TMP / name
    ws = v / "Projects" / "Alpha"
    (ws / "Log").mkdir(parents=True)
    (v / "Projects" / ".dev-workbook-version").write_text("3.8.0\n")
    if structured:
        (ws / ".vault-config.json").write_text("{}")
    if archive is not None:
        (v / "TasksArchive.md").write_text(archive)
    if progress is not None:
        (ws / "ProgressLog.md").write_text(progress)
    if log is not None:
        (ws / "Log" / f"{DATE}.md").write_text(log)
    return v


def tree(v: Path) -> dict[str, bytes]:
    return {str(p.relative_to(v)): p.read_bytes() for p in sorted(v.rglob("*")) if p.is_file() and ".git" not in p.parts}


def run(v: Path, payload: dict | str, *args: str, env: dict[str, str] | None = None, ws: str | None = "Projects/Alpha"):
    argv = [sys.executable, BIN, "closeout", "--vault", str(v), *(["--workspace", ws] if ws else []), *args]
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(argv, input=stdin, capture_output=True, text=True, env={**os.environ, **(env or {})})


def text(v: Path, rel: str) -> str:
    return (v / rel).read_text(encoding="utf-8")


def pay(**kw) -> dict:
    return {**PAYLOAD, **kw}


# ---------------------------------------------------------------------------
section("The day's log")
# ---------------------------------------------------------------------------

v = vault("log-new")
r = run(v, pay(decided=["[[DecisionNote]]"], learned=["a thing"], case_study=["a story — `slug` · mixed"], links=["PR https://x"]))
check(r.returncode == 0, "a new close-out exits 0", r.stderr)
expect = (f"---\ntype: log\ndate: {DATE}\n---\n\n# {DATE}\n\n- **Did:** built brief; wrote tests\n- **Decided:** [[DecisionNote]]\n"
          "- **Learned:** a thing\n- **Case study:** a story — `slug` · mixed\n- **Links:** PR https://x\n")
check(text(v, f"Projects/Alpha/Log/{DATE}.md") == expect, "a new log is in the template layout, lines in template order",
      text(v, f"Projects/Alpha/Log/{DATE}.md"))
check(f"Projects/Alpha/Log/{DATE}.md created did=+2 decided=+1 learned=+1 case_study=+1 links=+1" in r.stdout.splitlines(),
      "the output line names the file and the clause counts", r.stdout)
v = vault("log-minimal")
r = run(v, pay(did=["only this"]))
check(text(v, f"Projects/Alpha/Log/{DATE}.md").endswith("# 2026-11-23\n\n- **Did:** only this\n"),
      "lines with no clauses are omitted")

v = vault("log-merge", log=LOG_OLD)
before = tree(v)
r = run(v, pay(did=["Built brief", "wrote tests"], decided=["[[DecisionNote]]"], learned=["a thing"],
               case_study=["x — `s` · mixed"], links=["PR https://x", "[[Thread]]"]))
got = text(v, f"Projects/Alpha/Log/{DATE}.md")
check(got == (f"---\ntype: log\ndate: {DATE}\n---\n\n# {DATE}\n\n- **Did:** built brief; wrote tests\n- **Decided:** [[DecisionNote]]\n"
              "- **Learned:** a thing\n- **Case study:** x — `s` · mixed\n- **Links:** [[Thread]], PR https://x\n"),
      "a merge appends, inserts missing lines in template order and skips a duplicate", got)
check("did=+1 decided=+1 learned=+1 case_study=+1 links=+1 skipped=2" in r.stdout and "merged" in r.stdout, "the counts include skipped", r.stdout)
check(got.startswith(LOG_OLD.split("# 2026")[0]), "the frontmatter stays byte-identical")

v = vault("log-bold", log=f"---\ntype: log\ndate: {DATE}\n---\n\n# {DATE}\n\n- **Did:** **Built brief** and more\n")
r = run(v, pay(did=["built BRIEF"]))
check("unchanged" in r.stdout and text(v, f"Projects/Alpha/Log/{DATE}.md").endswith("**Built brief** and more\n"),
      "a clause differing only in case or bold is a duplicate", r.stdout)

v = vault("log-other", log=f"---\ntype: log\ndate: {DATE}\ntags: [x]\n---\n\n# {DATE}\n\nHand-written prose {MARKER}.\n\n- **Did:** a\n- **Links:** l\n\nTail.\n")
before_log = text(v, f"Projects/Alpha/Log/{DATE}.md")
run(v, pay(did=["b"], learned=["c"]))
got = text(v, f"Projects/Alpha/Log/{DATE}.md")
check(got == before_log.replace("- **Did:** a\n", "- **Did:** a; b\n- **Learned:** c\n"), "every other line and the frontmatter stay byte-identical", got)

# ---------------------------------------------------------------------------
section("ProgressLog")
# ---------------------------------------------------------------------------

v = vault("progress")
run(v, pay())
lines = [ln for ln in text(v, "Projects/Alpha/ProgressLog.md").split("\n") if ln.startswith("- ")]
check(lines[0] == "- **[[Alpha/Log/2026-11-23|2026-11-23]]** — Shipped the thing" and len(lines) == 3, "newest first: a new day goes on top", str(lines))
run(v, pay(date="2026-11-10", headline="Middle"))
dates = [ln.split("|")[1][:10] for ln in text(v, "Projects/Alpha/ProgressLog.md").split("\n") if ln.startswith("- ")]
check(dates == ["2026-11-23", "2026-11-20", "2026-11-10", "2026-11-05"], "an in-between day lands in date order", str(dates))
run(v, pay(date="2026-10-01", headline="Oldest"))
check(text(v, "Projects/Alpha/ProgressLog.md").rstrip().endswith("Oldest"), "an older day goes last")
run(v, pay(headline="Reworded headline"))
got = text(v, "Projects/Alpha/ProgressLog.md")
check(got.count("Log/2026-11-23|") == 1 and "Reworded headline" in got and "Shipped the thing" not in got, "a same-day line is replaced, not duplicated")
v = vault("progress-missing", progress=None)
r = run(v, pay())
got = text(v, "Projects/Alpha/ProgressLog.md")
check("progress-missing" not in got and got.startswith("---\ntype: log-index\nstatus: reference\n---\n\n# Progress log — Alpha\n")
      and got.endswith("— Shipped the thing\n") and "ProgressLog.md created" in r.stdout, "a missing ProgressLog is created from the template", got)

# ---------------------------------------------------------------------------
section("TasksArchive, fitted to the real file's shape")
# ---------------------------------------------------------------------------

v = vault("arch-year")
r = run(v, pay(date="2027-01-05", archive="Alpha year opened"))
got = text(v, "TasksArchive.md")
check(got.index("# Tasks Archive") < got.index("# 2027") < got.index("# 2026") and got.index("**Coverage starts") < got.index("# 2027"),
      "a new year goes below the intro, above the newest year", got[:700])
check("# 2027\n\n## Jan 2027\n\n### Month's Projects\n[[Alpha/Overview|alpha-kebab]]\n\n| Date | Tasks |\n| ---- | ----- |\n| 5    | Alpha year opened |\n\n# 2026"
      in got, "the new year is complete: month, projects line (alias reused), table, padded cell", got)

v = vault("arch-month")
run(v, pay(date="2026-12-02", archive="Alpha december"))
got = text(v, "TasksArchive.md")
check(got.index("## Dec 2026") < got.index("## Nov 2026") and got.index("# 2026") < got.index("## Dec 2026"),
      "a new month goes above the older one inside its year")
check("| 2    | Alpha december |" in got, "a one-digit day is padded like the existing cells")

v = vault("arch-sorted")
run(v, pay(date="2026-11-21", archive="Alpha sorted"))
rows = [ln.split("|")[1].strip() for ln in text(v, "TasksArchive.md").split("## Oct 2026")[0].split("\n") if ln.startswith("| ") and ln[2].isdigit()]
check(rows == ["22", "21", "20", "3"], "a sorted table gets the row in day order", str(rows))
v = vault("arch-end")
run(v, pay(date="2026-11-02", archive="Alpha early"))
rows = [ln.split("|")[1].strip() for ln in text(v, "TasksArchive.md").split("## Oct 2026")[0].split("\n") if ln.startswith("| ") and ln[2].isdigit()]
check(rows == ["22", "20", "3", "2"], "an earlier day goes at the end of a sorted table", str(rows))

v = vault("arch-unsorted")
r = run(v, pay(date="2026-10-28", archive="Alpha unsorted"))
oct_rows = [ln for ln in text(v, "TasksArchive.md").split("## Oct 2026")[1].split("## Sep 2026")[0].split("\n") if ln.startswith("| ") and ln[2].isdigit()]
check(oct_rows[0].startswith("| 28   |") and len(oct_rows) == 4, "an unsorted table gets the row at the top", str(oct_rows))
check("not in day order" in r.stderr, "and a warning on stderr", r.stderr)

v = vault("arch-extend")
r = run(v, pay(date="2026-11-20", archive="Alpha reviewed"))
check("| 20   | Bert thing, Alpha reviewed |" in text(v, "TasksArchive.md") and "row=extended" in r.stdout, "an existing row is extended, not duplicated", r.stdout)
r = run(v, pay(date="2026-11-20", archive="alpha REVIEWED"))
check("row=unchanged" in r.stdout and text(v, "TasksArchive.md").count("Alpha reviewed") == 1, "an existing clause is not added twice (case-folded)")
r = run(vault("arch-extend-bold"), pay(date="2026-11-03", archive="bert milestone"))
check("row=unchanged" in r.stdout, "a clause differing from a bold one only in bold is a duplicate", r.stdout)

v = vault("arch-link")
run(v, pay(date="2026-11-21", archive="Alpha link"))
nov = text(v, "TasksArchive.md").split("## Nov 2026")[1].split("## Oct 2026")[0]
check("[[Bert/Overview|Bert]], [[Other/Overview|other-thing]], [[Alpha/Overview|alpha-kebab]]" in nov and nov.count("Alpha/Overview") == 1,
      "the alias from an earlier month is reused, the link appended once", nov[:200])
run(v, pay(date="2026-11-21", archive="Alpha link two"))
check(text(v, "TasksArchive.md").split("## Nov 2026")[1].split("## Oct 2026")[0].count("Alpha/Overview") == 1,
      "a second close-out adds no second link to the same target")
v = vault("arch-link-oct")
r = run(v, pay(date="2026-10-28", archive="Alpha oct"))
check("link=+1" not in r.stdout and text(v, "TasksArchive.md").count("Alpha/Overview") == 1, "a month that already links the workspace gets no link", r.stdout)
v = vault("arch-project")
run(v, pay(date="2026-11-21", archive="Alpha proj", project="My Alpha"))
check("[[Alpha/Overview|My Alpha]]" in text(v, "TasksArchive.md").split("## Oct 2026")[0], "an explicit project is the alias")
v = vault("arch-fresh-alias", archive=ARCHIVE.replace("[[Alpha/Overview|alpha-kebab]]", "[[Other/Overview|x]]"))
run(v, pay(date="2026-11-21", archive="Alpha plain"))
check("[[Alpha/Overview|Alpha]]" in text(v, "TasksArchive.md"), "with no earlier alias the workspace folder name is used")
v = vault("arch-no-clause")
before = text(v, "TasksArchive.md")
r = run(v, pay(archive=None))
check(text(v, "TasksArchive.md") == before and "TasksArchive" not in r.stdout, "no archive clause: TasksArchive.md is not touched")

# ---------------------------------------------------------------------------
section("Clause text is written byte-exact")
# ---------------------------------------------------------------------------

nasty = "fixed `rm -rf $(whoami)` and ${HOME}, Caroline's naïve café — 日本語 \"quoted\" \\ back"
v = vault("nasty")
r = run(v, pay(did=[nasty], headline=nasty, archive="Alpha `$(id)` it's ünï"))
check(nasty in text(v, f"Projects/Alpha/Log/{DATE}.md") and f"— {nasty}\n" in text(v, "Projects/Alpha/ProgressLog.md")
      and "| 23   | Alpha `$(id)` it's ünï |" in text(v, "TasksArchive.md"), "backticks, $(), apostrophes and non-ASCII text land exactly", r.stderr)
check("sh: " not in r.stderr and "whoami" not in r.stdout, "nothing is executed")

# ---------------------------------------------------------------------------
section("Refusals exit 3 before any write")
# ---------------------------------------------------------------------------

v = vault("refuse")
(TMP / "outside-log").mkdir()
base = tree(v)
cases = [
    ("a bad date", pay(date="2026-13-01")), ("a short date", pay(date="2026-2-3")), ("an impossible date", pay(date="2026-02-30")),
    ("a missing date", {k: x for k, x in PAYLOAD.items() if k != "date"}), ("a missing headline", pay(headline="")),
    ("a newline in a clause", pay(did=["a\nb"])), ("a newline in the headline", pay(headline="a\nb")),
    ("a control character", pay(learned=["a\x1b[31mb"])), ("a pipe in archive", pay(archive="a | b")),
    ("a link in archive", pay(archive="a [[b]]")), ("an unsafe project", pay(project="a|b")),
    ("a non-list clause field", pay(did="oops")), ("an unknown field", {**PAYLOAD, "didd": []}),
    ("not JSON", "{nope"), ("a JSON array", "[1]"), ("empty stdin", ""),
]
for label, payload in cases:
    r = run(v, payload)
    check(r.returncode == 3 and r.stderr.startswith("closeout: ") and r.stdout == "" and tree(v) == base,
          f"refuses {label}", f"rc={r.returncode} {r.stderr!r}")
for label, ws in (("a workspace outside Projects/", "Resources/Alpha"), ("a traversal", "Projects/../x"), ("a missing workspace", "Projects/Nope")):
    r = run(v, pay(), ws=ws)
    check(r.returncode == 3 and tree(v) == base, f"refuses {label}", r.stderr)
r = run(vault("refuse-unstructured", structured=False), pay())
check(r.returncode == 3 and "structured" in r.stderr, "refuses an unstructured workspace", r.stderr)
r = run(v, pay(), ws=None)
check(r.returncode == 3 and "no structured workspace" in r.stderr, "refuses when the repo maps to no workspace", r.stderr)
v2 = vault("refuse-noarchive", archive=None)
b2 = tree(v2)
r = run(v2, pay())
check(r.returncode == 3 and "TasksArchive.md is missing" in r.stderr and tree(v2) == b2, "refuses a missing TasksArchive.md when archive is set", r.stderr)
r = run(v2, pay(archive=None))
check(r.returncode == 0, "a missing TasksArchive.md is fine without an archive clause", r.stderr)
v3 = vault("refuse-link")
import shutil  # noqa: E402
shutil.rmtree(v3 / "Projects" / "Alpha" / "Log")
(v3 / "Projects" / "Alpha" / "Log").symlink_to(TMP / "outside-log")
r = run(v3, pay())
check(r.returncode == 3 and "outside the vault" in r.stderr and not list((TMP / "outside-log").iterdir()), "refuses a target that resolves outside the vault", r.stderr)
r = run(v, pay(), "--bogus")
check(r.returncode == 3, "refuses an unknown argument")

# ---------------------------------------------------------------------------
section("Modes")
# ---------------------------------------------------------------------------

v = vault("dry")
base = tree(v)
r = run(v, pay(), "--dry-run")
check(r.returncode == 0 and tree(v) == base and "created" in r.stdout and "dry-run" in r.stdout, "--dry-run writes nothing and reports what would happen", r.stdout)

v = vault("idem", log=LOG_OLD)
r1 = run(v, pay(learned=["x"], case_study=["c — `s` · success"], links=["l"]))
t1 = tree(v)
r2 = run(v, pay(learned=["x"], case_study=["c — `s` · success"], links=["l"]))
check(tree(v) == t1 and all(" unchanged" in ln for ln in r2.stdout.splitlines()) and len(r2.stdout.splitlines()) == 3,
      "a rerun is byte-idempotent and reports every file unchanged", r2.stdout)

bg = {"CLAUDE_JOB_DIR": str(TMP / "job"), "CLAUDE_CODE_SESSION_ID": "sess-1"}
v = vault("bg", log=LOG_OLD)
base = tree(v)
r = run(v, pay(learned=["bg thing"]), env=bg)
spool = TMP / "state" / "dev-workbook" / "spool" / "sess-1" / "notes"
check(r.returncode == 0 and tree(v) == base, "a background session leaves the vault untouched", r.stderr)
check("bg thing" in (spool / "Projects/Alpha/Log" / f"{DATE}.md").read_text() and "Alpha brief built" in (spool / "TasksArchive.md").read_text()
      and (spool / "Projects/Alpha/ProgressLog.md").is_file(), "and writes all three files to the spool")
r = run(v, pay(learned=["bg thing"]), env=bg)
check(r.returncode == 0 and all(" unchanged" in ln for ln in r.stdout.splitlines()), "a background rerun merges into the staged copies: unchanged", r.stdout)
r = run(v, pay(), env={"CLAUDE_JOB_DIR": str(TMP / "job")})
check(r.returncode == 3 and "cannot stage" in r.stderr and tree(v) == base, "background without a session id refuses, never writes the vault", r.stderr)

# ---------------------------------------------------------------------------
section("--commit")
# ---------------------------------------------------------------------------


def git(v: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(v), *args], capture_output=True, text=True, check=True).stdout.strip()


def git_vault(name: str, remote: bool = True) -> Path:
    v = vault(name, log=LOG_OLD)
    git(v, "init", "-q", "-b", "main")
    (v / "Stray.md").write_text("not the plugin's\n")
    (v / "Scratch").mkdir()
    (v / "Scratch" / "n.md").write_text("x\n")
    git(v, "add", "Projects", "TasksArchive.md")
    git(v, "commit", "-q", "-m", "init")
    if remote:
        bare = TMP / f"{name}-remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        git(v, "remote", "add", "origin", str(bare))
        git(v, "push", "-q", "-u", "origin", "main")
    return v


v = git_vault("commit")
r = run(v, pay(learned=["committed"]), "--commit")
last = r.stdout.strip().splitlines()[-1]
check(r.returncode == 0 and last.startswith("commit=") and last.endswith("pushed=yes") and "commit=none" not in last, "commits and pushes: commit=<sha> pushed=yes", r.stdout + r.stderr)
check(git(v, "rev-list", "--count", "origin/main..HEAD") == "0" and git(v, "rev-list", "--count", "HEAD") == "2", "one new commit, on the remote")
files = git(v, "show", "--name-only", "--format=", "HEAD").split("\n")
check(f"Projects/Alpha/Log/{DATE}.md" in files and "TasksArchive.md" in files and "Stray.md" not in files
      and not any(f.startswith("Scratch") for f in files), "it touches owned paths only", str(files))
check(git(v, "log", "-1", "--format=%B") == f"vault: session updates {__import__('time').strftime('%Y-%m-%d')}", "the hook's single-line commit")
check("not committing" in r.stdout, "the hook's report is passed on", r.stdout)
r = run(v, pay(learned=["committed"]), "--commit")
check(r.stdout.strip().splitlines()[-1] == "commit=none pushed=yes", "with nothing to commit: commit=none", r.stdout)
r = run(git_vault("commit-local", remote=False), pay(), "--commit")
check(r.stdout.strip().splitlines()[-1].endswith("commit=" + git(TMP / "commit-local", "rev-parse", "--short", "HEAD") + " pushed=no-remote"),
      "a vault with no remote: pushed=no-remote", r.stdout)
v = git_vault("commit-dry")
head = git(v, "rev-parse", "HEAD")
r = run(v, pay(), "--commit", "--dry-run")
check(git(v, "rev-parse", "HEAD") == head and r.stdout.strip().splitlines()[-1] == "commit=none dry-run", "--commit with --dry-run commits nothing")
v = vault("commit-none")
base = tree(v)
r = run(v, pay(), "--commit")
check(r.stdout.strip().splitlines()[-1] == "commit=none sync=none" and (v / "Projects/Alpha/Log" / f"{DATE}.md").is_file(), "sync=none: files written, nothing committed", r.stdout)
v = git_vault("commit-hooks")
(v / ".git" / "dev-workbook-hooks").write_text("now\n")
head = git(v, "rev-parse", "HEAD")
r = run(v, pay(), "--commit")
check(r.stdout.strip().splitlines()[-1] == "commit=none sync=hooks" and git(v, "rev-parse", "HEAD") == head, "sync=hooks: the hooks commit, not closeout", r.stdout)
v = git_vault("commit-bg")
head = git(v, "rev-parse", "HEAD")
r = run(v, pay(), "--commit", env={**bg, "CLAUDE_CODE_SESSION_ID": "sess-2"})
check(r.stdout.strip().splitlines()[-1:] == ["commit=none background=yes"] and git(v, "rev-parse", "HEAD") == head, "a background session never commits", f"{r.returncode} {r.stdout!r} {r.stderr!r}")

# ---------------------------------------------------------------------------
section("Output never carries vault text")
# ---------------------------------------------------------------------------

v = vault("marker", log=LOG_OLD + f"- **Learned:** {MARKER}\n")
r = run(v, pay(date="2026-11-20", archive="Alpha marker check"))
r2 = run(v, pay(learned=["z"]))
check(MARKER not in r.stdout + r.stderr + r2.stdout + r2.stderr, "a marker planted in the log, ProgressLog and TasksArchive never reaches the output")
check(len(r.stdout.splitlines()) == 3 and all(ln.split()[1] in ("created", "merged", "unchanged") for ln in r.stdout.splitlines()),
      "one line per file: <path> created|merged|unchanged", r.stdout)
r = subprocess.run([sys.executable, BIN, "closeout", "--vault", str(vault("sub")), "--workspace", "Projects/Alpha"],
                   input=json.dumps(pay()), capture_output=True, text=True)
check(r.returncode == 0 and r.stdout.startswith("Projects/Alpha/Log/"), "bin/dev-workbook closeout runs as a subprocess", r.stderr)

print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

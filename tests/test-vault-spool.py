#!/usr/bin/env python3
"""Regression tests for hooks/vault_spool.py — background-session notes staged outside the vault.

A background session cannot Write/Edit the vault's git checkout, so it stages notes in a spool and
the session hooks merge them in once it has ended. The protection under test: nothing the user or
another session wrote meanwhile is ever overwritten. Run directly:

    python3 tests/test-vault-spool.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import vault_spool as vs  # noqa: E402

PASS = 0
FAIL: list[str] = []


def ok(name: str) -> None:
    global PASS
    PASS += 1
    print(f"  \033[32mok\033[0m   {name}")


def bad(name: str, detail: str = "") -> None:
    FAIL.append(name)
    print(f"  \033[31mFAIL\033[0m {name}")
    if detail:
        print(f"       {detail}")


def check(cond: bool, name: str, detail: str = "") -> None:
    ok(name) if cond else bad(name, detail)


def section(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")


TMP = Path(tempfile.mkdtemp(prefix="dev-workbook-spool."))
os.environ["XDG_STATE_HOME"] = str(TMP / "state")
os.environ.pop("CLAUDE_PID", None)
DEAD_PID = None


def dead_pid() -> str:
    global DEAD_PID
    if DEAD_PID is None:
        p = subprocess.Popen(["true"])
        p.wait()
        DEAD_PID = str(p.pid)
    return DEAD_PID


def vault(name: str) -> Path:
    v = TMP / name
    (v / "Projects" / "Alpha" / "Log").mkdir(parents=True)
    return v


def staged(v: Path, rel: str, sid: str, pid: str | None = None) -> Path:
    """Stage as session `sid`, owned by `pid` (a dead one by default, so the spool is due)."""
    os.environ["CLAUDE_PID"] = pid or dead_pid()
    try:
        path, msg = vs.stage(v, rel, sid)
    finally:
        os.environ.pop("CLAUDE_PID", None)
    assert path is not None, msg
    return path


def spool(sid: str) -> Path:
    return vs.spool_root() / sid


LOG = "---\ntype: log\ndate: 2026-11-05\n---\n\n# 2026-11-05\n\n- **Did:** first\n"

# ---------------------------------------------------------------------------
section("Staging only accepts what the vault hooks publish")
# ---------------------------------------------------------------------------

v = vault("paths")
for rel in ("Projects/Alpha/Notes/A.md", "Resources/R.md", "Contributions/C.md", "Home.md",
            "Projects/Alpha/.vault-config.json"):
    check(vs.check_path(rel) == rel, f"accepted: {rel}")
for rel in ("Notes/Stray.md", "/etc/passwd", "../Out.md", "Projects/../Home.md", "Projects/A/.env",
            "Projects/A/key.pem", "Archived/Old.md", "Random.md", "Projects"):
    check(vs.check_path(rel) is None, f"refused: {rel}")

(TMP / "outside").mkdir()
(v / "Projects" / "Link").symlink_to(TMP / "outside")
path, msg = vs.stage(v, "Projects/Link/Escape.md", "s-link")
check(path is None and "outside" in msg, "a symlink out of the vault is refused", msg)

os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
path, msg = vs.stage(v, "Projects/Alpha/Notes/A.md")
check(path is None and "session" in msg, "no session id, no staging", msg)

# ---------------------------------------------------------------------------
section("Stage copies the note twice; staging again keeps the first base")
# ---------------------------------------------------------------------------

v = vault("stage")
note = v / "Projects" / "Alpha" / "Overview.md"
note.write_text("# Alpha\n\noriginal\n")
work = staged(v, "Projects/Alpha/Overview.md", "s-stage")
check(work.read_text() == "# Alpha\n\noriginal\n", "the working copy starts as the vault note")
check((spool("s-stage") / "base" / "Projects/Alpha/Overview.md").read_text() == "# Alpha\n\noriginal\n",
      "the base is recorded")
work.write_text("# Alpha\n\nedited\n")
note.write_text("# Alpha\n\nchanged meanwhile\n")
again = staged(v, "Projects/Alpha/Overview.md", "s-stage")
check(again == work and work.read_text() == "# Alpha\n\nedited\n", "staging again keeps the edits")
check((spool("s-stage") / "base" / "Projects/Alpha/Overview.md").read_text() == "# Alpha\n\noriginal\n",
      "staging again keeps the first base")
check(note.read_text() == "# Alpha\n\nchanged meanwhile\n", "staging never writes the vault")

new = staged(v, "Projects/Alpha/Notes/Fresh.md", "s-stage")
check(not new.exists() and new.parent.is_dir(), "a new note: its folder is made, the file is not")

other = vault("other")
path, msg = vs.stage(other, "Home.md", "s-stage")
check(path is None and "another vault" in msg, "a session's spool is tied to one vault", msg)

# ---------------------------------------------------------------------------
section("Apply: replace, create, merge")
# ---------------------------------------------------------------------------

v = vault("apply")
(v / "Projects/Alpha/Overview.md").write_text("# Alpha\n\nline one\n\nline two\n\nline three\n")
w = staged(v, "Projects/Alpha/Overview.md", "s-apply")
w.write_text("# Alpha\n\nline one, edited in the background\n\nline two\n\nline three\n")
new = staged(v, "Projects/Alpha/Notes/Fresh.md", "s-apply")
new.write_text("# Fresh\n")
untouched = staged(v, "Home.md", "s-apply")  # Home.md does not exist and is never written
msgs = vs.apply(v)
check((v / "Projects/Alpha/Overview.md").read_text().startswith("# Alpha\n\nline one, edited"),
      "a note untouched in the vault is replaced")
check((v / "Projects/Alpha/Notes/Fresh.md").read_text() == "# Fresh\n", "a new note is created")
check(not (v / "Home.md").exists(), "a note staged but never written is not created")
check(not spool("s-apply").exists(), "a fully applied spool is removed")
check(any("applied 2 note(s)" in m for m in msgs), "the apply is reported", repr(msgs))

v = vault("merge")
target = v / "Projects/Alpha/Overview.md"
target.write_text("# Alpha\n\nline one\n\nline two\n\nline three\n")
w = staged(v, "Projects/Alpha/Overview.md", "s-merge")
w.write_text("# Alpha\n\nline one, background\n\nline two\n\nline three\n")
target.write_text("# Alpha\n\nline one\n\nline two\n\nline three, user\n")
vs.apply(v)
check(target.read_text() == "# Alpha\n\nline one, background\n\nline two\n\nline three, user\n",
      "edits to different parts of a note both survive", repr(target.read_text()))

# ---------------------------------------------------------------------------
section("Apply never clobbers")
# ---------------------------------------------------------------------------

v = vault("clash")
target = v / "Projects/Alpha/Overview.md"
target.write_text("# Alpha\n\nshared line\n")
w = staged(v, "Projects/Alpha/Overview.md", "s-clash")
w.write_text("# Alpha\n\nshared line, background version\n")
target.write_text("# Alpha\n\nshared line, user version\n")
msgs = vs.apply(v)
check(target.read_text() == "# Alpha\n\nshared line, user version\n", "a conflicting edit leaves the vault note alone")
check(w.read_text() == "# Alpha\n\nshared line, background version\n", "and keeps the background version in the spool")
check(any("do not merge" in m and "Projects/Alpha/Overview.md" in m for m in msgs), "and reports it", repr(msgs))
check(vs.apply(v) == [], "a held conflict is reported once, not every session")
check(any("held" in line for line in vs.pending(v)), "`staged` lists it as held")

v = vault("both-created")
w = staged(v, "Projects/Alpha/Notes/Same.md", "s-both")
w.write_text("# Background\n")
(v / "Projects/Alpha/Notes").mkdir(parents=True, exist_ok=True)
(v / "Projects/Alpha/Notes/Same.md").write_text("# User\n")
vs.apply(v)
check((v / "Projects/Alpha/Notes/Same.md").read_text() == "# User\n", "a note created on both sides keeps the vault's")

v = vault("deleted")
(v / "Projects/Alpha/Gone.md").write_text("# Gone\n")
w = staged(v, "Projects/Alpha/Gone.md", "s-deleted")
w.write_text("# Gone, edited\n")
(v / "Projects/Alpha/Gone.md").unlink()
vs.apply(v)
check(not (v / "Projects/Alpha/Gone.md").exists(), "a note deleted in the vault is not resurrected")

v = vault("planted")
sp = spool("s-planted")
(sp / "notes" / "Notes").mkdir(parents=True)
(sp / "notes" / "Notes" / "Stray.md").write_text("x\n")
vs.save_meta(sp, {"vault": str(v.resolve()), "session": "s-planted", "pid": dead_pid()})
msgs = vs.apply(v)
check(not (v / "Notes").exists(), "a path the hooks do not publish is never written")
check(any("do not publish" in m for m in msgs), "and is reported", repr(msgs))

# ---------------------------------------------------------------------------
section("Logs: both sessions' entries are kept")
# ---------------------------------------------------------------------------

v = vault("log")
log = v / "Projects/Alpha/Log/2026-11-05.md"
log.write_text(LOG)
w = staged(v, "Projects/Alpha/Log/2026-11-05.md", "s-log")
w.write_text(LOG + "- **Did:** background entry\n")
log.write_text(LOG + "- **Did:** user entry\n")
vs.apply(v)
text = log.read_text()
check("background entry" in text and "user entry" in text and "<<<<<<<" not in text,
      "appends to the same log from both sides are both kept", repr(text))
check(text.count("type: log") == 1, "the frontmatter is not duplicated")

v = vault("log-fm")
log = v / "Projects/Alpha/Log/2026-11-05.md"
log.write_text(LOG)
w = staged(v, "Projects/Alpha/Log/2026-11-05.md", "s-logfm")
w.write_text(LOG.replace("type: log", "type: log\nstatus: background"))
log.write_text(LOG.replace("type: log", "type: log\nstatus: user"))
vs.apply(v)
check("status: user" in log.read_text() and "status: background" not in log.read_text(),
      "a frontmatter conflict in a log is held, not unioned")

v = vault("log-top")
log = v / "Projects/Alpha/Log/2026-11-05.md"
log.write_text(LOG)
w = staged(v, "Projects/Alpha/Log/2026-11-05.md", "s-logtop")
w.write_text("---\ntype: background\n" + LOG[len("---\ntype: log\n"):])
log.write_text("---\ntype: user\n" + LOG[len("---\ntype: log\n"):])
vs.apply(v)
check(log.read_text().count("---\n") == 2 and "type: background" not in log.read_text(),
      "a conflict at the top of a log's frontmatter is held, not unioned")

v = vault("note-union")
target = v / "Projects/Alpha/Overview.md"
target.write_text("# Alpha\n\nend\n")
w = staged(v, "Projects/Alpha/Overview.md", "s-nu")
w.write_text("# Alpha\n\nend\n- background\n")
target.write_text("# Alpha\n\nend\n- user\n")
vs.apply(v)
check(target.read_text() == "# Alpha\n\nend\n- user\n", "a non-log note is never unioned")

# ---------------------------------------------------------------------------
section("Only finished sessions are applied")
# ---------------------------------------------------------------------------

v = vault("live")
(v / "Projects/Alpha/Overview.md").write_text("old\n")
w = staged(v, "Projects/Alpha/Overview.md", "s-live", pid=str(os.getpid()))
w.write_text("new\n")
vs.apply(v)
check((v / "Projects/Alpha/Overview.md").read_text() == "old\n", "a running session's spool is left alone")
check(any("running" in line for line in vs.pending(v)), "`staged` lists it as running")
vs.apply(v, "s-live")
check((v / "Projects/Alpha/Overview.md").read_text() == "new\n", "its own session end applies it")

v = vault("nopid")
(v / "Projects/Alpha/Overview.md").write_text("old\n")
path, _ = vs.stage(v, "Projects/Alpha/Overview.md", "s-nopid")
path.write_text("new\n")
vs.apply(v)
check((v / "Projects/Alpha/Overview.md").read_text() == "old\n", "no owner pid: a fresh spool waits")
old = 1_000_000_000
for p in spool("s-nopid").rglob("*"):
    os.utime(p, (old, old))
vs.apply(v)
check((v / "Projects/Alpha/Overview.md").read_text() == "new\n", "no owner pid: an idle spool is applied")

v = vault("busy")
subprocess.run(["git", "init", "-q", str(v)], check=True)
(v / "Projects/Alpha/Overview.md").write_text("old\n")
w = staged(v, "Projects/Alpha/Overview.md", "s-busy")
w.write_text("new\n")
gitdir = subprocess.run(["git", "-C", str(v), "rev-parse", "--absolute-git-dir"],
                        capture_output=True, text=True).stdout.strip()
Path(gitdir, "MERGE_HEAD").write_text("0" * 40 + "\n")
msgs = vs.apply(v)
check((v / "Projects/Alpha/Overview.md").read_text() == "old\n", "nothing is applied mid-merge")
check(any("merge in progress" in m for m in msgs), "and that is reported", repr(msgs))

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

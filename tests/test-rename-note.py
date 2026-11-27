#!/usr/bin/env python3
"""Tests for scripts/rename_note.py — renaming a vault note without breaking references.

    python3 tests/test-rename-note.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import rename_note as rn  # noqa: E402

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


def section(t: str) -> None:
    print(f"\n\033[1m{t}\033[0m")


def write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def git(v: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(v), *args], check=True, capture_output=True)


def build(root: Path, versioned: bool = True) -> Path:
    v = root / "vault"
    a = v / "Projects" / "Alpha"
    write(a / "Decisions" / "use-old-host.md",
          "---\ntype: decision\nstatus: superseded\nsuperseded_by: UseNewHost\n---\n\n# Use old host\n")
    write(a / "Decisions" / "UseNewHost.md",
          "---\ntype: decision\nstatus: active\nsupersedes: use-old-host\n---\n\n# Use new host\n")
    write(a / "Decisions" / "UseNewerHost.md",
          "---\ntype: decision\nstatus: active\nsupersedes: [use-old-host, other-thing]\n---\n\n# Newer\n")
    write(a / "Decisions" / "BlockList.md",
          "---\ntype: decision\nsupersedes:\n  - use-old-host\n  - use-old-host-two\n---\n\n# Block\n")
    write(a / "Log" / "2026-10-01.md",
          "# 2026-10-01\n\n- [[use-old-host]], [[use-old-host|the old one]], [[use-old-host#Why]]\n"
          "- [[Projects/Alpha/Decisions/use-old-host]] and [[Alpha/use-old-host]]\n"
          "- not this: [[use-old-host-two]] or [[Beta/use-old-host]]\n"
          "- forms: [[Use-Old-Host]] [[use-old-host.md|md]] [[Decisions/USE-OLD-HOST.MD]]\n"
          "| a | [[use-old-host\\|cell]] |\n")
    write(a / "Threads" / "shared-name.md", "# Alpha's shared\n")
    write(a / "Overview.md", "# Alpha\n\n- [[shared-name]]\n")
    write(v / "Projects" / "Beta" / "Threads" / "shared-name.md", "# Beta's shared\n")
    write(v / "Projects" / "Beta" / "Overview.md", "# Beta\n\n- [[shared-name]] and [[Alpha/Threads/shared-name]]\n")
    write(v / "Resources" / "Elsewhere.md", "See [[use-old-host]].\n")
    write(v / "Archived" / "old" / "Note.md", "History: [[use-old-host]].\n")
    if versioned:
        git(v, "init", "-q")
        git(v, "config", "user.email", "t@example.invalid")
        git(v, "config", "user.name", "T")
        git(v, "add", "-A")
        git(v, "commit", "-qm", "seed")
    return v


tmp = Path(tempfile.mkdtemp(prefix="dev-workbook-rn-tests."))
try:
    section("Every link form is rewritten")
    v = build(tmp / "a")
    links, files = rn.rename(v, "Projects/Alpha/Decisions/use-old-host.md",
                             "Projects/Alpha/Decisions/UseOldHost.md")
    log = (v / "Projects/Alpha/Log/2026-10-01.md").read_text()
    check("[[UseOldHost]]," in log, "bare link")
    check("[[UseOldHost|the old one]]" in log, "aliased link")
    check("[[UseOldHost#Why]]" in log, "heading link")
    check("[[UseOldHost\\|cell]]" in log, "escaped alias inside a table")
    check(log.split("- forms:")[0].count("[[UseOldHost]]") == 3,
          "path-qualified links to the note become bare", log)
    check("- forms: [[UseOldHost]] [[UseOldHost|md]] [[UseOldHost]]\n" in log,
          "case variants and a .md suffix are rewritten", log)
    check("[[use-old-host-two]]" in log, "a longer name sharing the prefix is untouched")
    check("[[Beta/use-old-host]]" in log, "a path into another workspace is untouched")
    check("[[UseOldHost]]" in (v / "Resources/Elsewhere.md").read_text(),
          "a unique name is rewritten outside the workspace too")
    check("[[use-old-host]]" in (v / "Archived/old/Note.md").read_text(), "Archived/ is never edited")

    section("Supersession frontmatter follows the rename")
    check("supersedes: UseOldHost" in (v / "Projects/Alpha/Decisions/UseNewHost.md").read_text(),
          "scalar supersedes:")
    newer = (v / "Projects/Alpha/Decisions/UseNewerHost.md").read_text()
    check("supersedes: [UseOldHost, other-thing]" in newer, "inline list supersedes:", newer)
    block = (v / "Projects/Alpha/Decisions/BlockList.md").read_text()
    check("  - UseOldHost\n  - use-old-host-two" in block, "block list, without touching a longer name", block)

    section("The file moves, through git in a versioned vault")
    check((v / "Projects/Alpha/Decisions/UseOldHost.md").is_file()
          and not (v / "Projects/Alpha/Decisions/use-old-host.md").exists(), "file renamed")
    st = subprocess.run(["git", "-C", str(v), "status", "--short"], capture_output=True, text=True).stdout
    check("R  Projects/Alpha/Decisions/use-old-host.md -> Projects/Alpha/Decisions/UseOldHost.md" in st,
          "staged as a git rename", st)

    section("A name shared with another workspace is rewritten only at home")
    rn.rename(v, "Projects/Alpha/Threads/shared-name.md", "Projects/Alpha/Threads/AlphaSharedName.md")
    check("[[AlphaSharedName]]" in (v / "Projects/Alpha/Overview.md").read_text(),
          "bare link inside the renamed note's workspace")
    beta = (v / "Projects/Beta/Overview.md").read_text()
    check("[[shared-name]]" in beta, "bare link in another workspace keeps meaning its own note", beta)
    check("[[AlphaSharedName]]" in beta, "path-qualified link from another workspace is rewritten", beta)

    section("A path-qualified link into another workspace's same-named folder is left alone")
    write(v / "Projects/Alpha/Log/2026-10-05.md", "# Alpha day\n")
    write(v / "Projects/Beta/Log/2026-10-05.md", "# Beta day\n")
    write(v / "Projects/Beta/ProgressLog.md", "- [[Log/2026-10-05]] and [[2026-10-05]]\n")
    write(v / "Projects/Alpha/ProgressLog.md", "- [[Log/2026-10-05]]\n")
    rn.rename(v, "Projects/Alpha/Log/2026-10-05.md", "Projects/Alpha/Log/2026-10-06.md")
    beta_log = (v / "Projects/Beta/ProgressLog.md").read_text()
    check(beta_log == "- [[Log/2026-10-05]] and [[2026-10-05]]\n",
          "Beta's [[Log/...]] still means Beta's own log", beta_log)
    check("[[2026-10-06]]" in (v / "Projects/Alpha/ProgressLog.md").read_text(),
          "Alpha's own link follows the rename, bare once the date is unique")
    rn.rename(v, "Projects/Alpha/Log/2026-10-06.md", "Projects/Alpha/Log/2026-10-05.md")
    check("[[Alpha/Log/2026-10-05]]" in (v / "Projects/Alpha/ProgressLog.md").read_text(),
          "a rename onto a shared name writes the shortest unique path")

    section("Moving between folders")
    rn.rename(v, "Projects/Alpha/Decisions/UseNewHost.md", "Projects/Alpha/Playbooks/NewHostPlaybook.md")
    check((v / "Projects/Alpha/Playbooks/NewHostPlaybook.md").is_file(), "target folder is created")
    check("superseded_by: NewHostPlaybook" in (v / "Projects/Alpha/Decisions/UseOldHost.md").read_text(),
          "superseded_by follows a move too")

    section("Refusals change nothing")
    before = {p: p.read_bytes() for p in v.rglob("*.md")}
    for old, new, why in [
        ("Projects/Alpha/Decisions/Nope.md", "Projects/Alpha/Decisions/X.md", "missing source"),
        ("Projects/Alpha/Decisions/UseOldHost.md", "Projects/Alpha/Decisions/UseNewerHost.md", "existing target"),
        ("Projects/Alpha/Decisions/UseOldHost.md", "Projects/Alpha/Decisions/UseOldHost.txt", "non-markdown target"),
    ]:
        try:
            rn.rename(v, old, new)
            check(False, f"{why}: refused")
        except ValueError:
            check(True, f"{why}: refused")
    check(before == {p: p.read_bytes() for p in v.rglob("*.md")}, "no file changed by a refused rename")

    section("Paths that leave the vault are refused")
    outside = tmp / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("key\n")
    (v / "Projects/Alpha/Shared").symlink_to(outside)
    before = {p: p.read_bytes() for p in v.rglob("*.md")}
    for old_p, new_p, why in [
        ("Projects/Alpha/Decisions/UseOldHost.md", "../outside/Stolen.md", "a .. target"),
        ("Projects/Alpha/Decisions/UseOldHost.md", str(outside / "Abs.md"), "an absolute target"),
        ("Projects/Alpha/Decisions/UseOldHost.md", "Projects/Alpha/Shared/In.md", "a target through a symlink"),
        ("Projects/Alpha/Shared/secret.txt", "Resources/Pulled.md", "a source through a symlink"),
        ("../outside/secret.txt", "Resources/Pulled.md", "a .. source"),
        ("Projects/Alpha/Decisions/UseOldHost.md", ".git/Hidden.md", "a dot-directory target"),
    ]:
        try:
            rn.rename(v, old_p, new_p)
            check(False, f"{why}: refused")
        except ValueError:
            check(True, f"{why}: refused")
    check(before == {p: p.read_bytes() for p in v.rglob("*.md")} and sorted(x.name for x in outside.iterdir()) == ["secret.txt"],
          "nothing moved in or out, and no link rewritten")
    (v / "Projects/Alpha/Shared").unlink()

    section("A failed move rewrites no link")
    write(v / "-n.md", "# dash\n")
    write(v / "Resources/LinksDash.md", "see [[-n]]\n")
    git(v, "add", "-A")
    git(v, "commit", "-qm", "dash")
    rn.rename(v, "-n.md", "Resources/Dashed.md")
    check((v / "Resources/Dashed.md").is_file() and "[[Dashed]]" in (v / "Resources/LinksDash.md").read_text(),
          "a note named like an option is moved by git mv --")
    write(v / "Resources/Blocker.md", "# b\n")
    import unittest.mock as um
    before = {p: p.read_bytes() for p in v.rglob("*.md")}
    real_run = rn.subprocess.run

    def failing_mv(cmd, *a, **k):
        if "mv" in cmd:
            return rn.subprocess.CompletedProcess(cmd, 1, "", "fatal: boom")
        return real_run(cmd, *a, **k)

    with um.patch.object(rn.subprocess, "run", side_effect=failing_mv):
        try:
            rn.rename(v, "Resources/Dashed.md", "Resources/Dashed2.md")
        except Exception:
            pass
    check(before == {p: p.read_bytes() for p in v.rglob("*.md")}, "a refused git mv leaves every link as it was")

    section("Dry run")
    before = {p: p.read_bytes() for p in v.rglob("*.md")}
    links, files = rn.rename(v, "Projects/Alpha/Decisions/UseOldHost.md",
                             "Projects/Alpha/Decisions/UseOriginalHost.md", dry_run=True)
    check(links > 0 and before == {p: p.read_bytes() for p in v.rglob("*.md")}
          and (v / "Projects/Alpha/Decisions/UseOldHost.md").exists(),
          "reports counts and writes nothing", f"{links} links")

    section("Unversioned vault")
    u = build(tmp / "u", versioned=False)
    rn.rename(u, "Projects/Alpha/Decisions/use-old-host.md", "Projects/Alpha/Decisions/UseOldHost.md")
    check((u / "Projects/Alpha/Decisions/UseOldHost.md").is_file()
          and "[[UseOldHost]]" in (u / "Resources/Elsewhere.md").read_text(),
          "plain move plus link rewrite without git")

    section("CLI")
    rc = rn.main(["--vault", str(u), "Projects/Alpha/Decisions/Missing.md", "Projects/Alpha/Decisions/X.md"])
    check(rc == 1, "a refused rename exits 1", str(rc))
    rc = rn.main(["--vault", str(tmp / "nowhere"), "a.md", "b.md"])
    check(rc == 2, "a missing vault exits 2", str(rc))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if not FAIL:
    print(f"\033[32m{PASS} passed\033[0m")
    sys.exit(0)
print(f"\033[31m{len(FAIL)} failed\033[0m, {PASS} passed")
for n in FAIL:
    print(f"  - {n}")
sys.exit(1)

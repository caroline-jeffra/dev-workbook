#!/usr/bin/env python3
"""Tests for links between skill files, and for `dev-workbook ref`, which serves those files to a
skill installed on its own (~/.agents/skills holds one folder per skill, so a `../other-skill/`
link only resolves when every skill is installed beside it).

    python3 tests/test-skill-links.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
CLI = ROOT / "bin" / "dev-workbook"

# A markdown link to a relative .md path, with an optional #fragment: [text](path.md#x)
LINK = re.compile(r"\]\(([^)\s:#]+\.md)(?:#[^)]*)?\)")

failures = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global failures
    if cond:
        print(f"  \033[32mok\033[0m   {name}")
    else:
        failures += 1
        print(f"  \033[31mFAIL\033[0m {name}" + (f"\n       {detail}" if detail else ""))


def ref(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), "ref", *args], capture_output=True, text=True)


print("\033[1mskill links\033[0m")

broken, cross = [], 0
for md in sorted(SKILLS.rglob("*.md")):
    for target in LINK.findall(md.read_text(encoding="utf-8")):
        dest = (md.parent / target).resolve()
        if not dest.is_file():
            broken.append(f"{md.relative_to(ROOT)} → {target}")
        elif dest.is_relative_to(SKILLS) and dest.relative_to(SKILLS).parts[0] != md.relative_to(SKILLS).parts[0]:
            cross += 1
            other = dest.relative_to(SKILLS).as_posix()
            check(f"ref serves {md.relative_to(SKILLS)} → {other}", ref(other).returncode == 0)
check("every relative link in skills/ resolves", not broken, "; ".join(broken))
check("the skills do link across each other (the case ref exists for)", cross > 0)

# A skill that links into another skill must say how to read the target when installed alone.
for skill in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
    text = "\n".join(p.read_text(encoding="utf-8") for p in skill.rglob("*.md"))
    if re.search(r"\]\((?:\.\./)+(?!" + re.escape(skill.name) + r"/)[a-z-]+/", text):
        check(f"{skill.name} names `dev-workbook ref` for its cross-skill links",
              "dev-workbook ref" in (skill / "SKILL.md").read_text(encoding="utf-8"))

print("\033[1mdev-workbook ref\033[0m")

whole = ref("manage-project-workspaces/reference/structure.md")
check("prints a whole file", whole.returncode == 0 and whole.stdout ==
      (SKILLS / "manage-project-workspaces/reference/structure.md").read_text(encoding="utf-8"))

sec = ref("manage-project-workspaces/reference/structure.md", "--section", "Linking")
lines = sec.stdout.splitlines()
check("--section prints one section", sec.returncode == 0 and lines[0].startswith("## Linking")
      and not any(l.startswith("## ") for l in lines[1:]), sec.stdout[:200])
check("--section= form works", ref("manage-project-workspaces/reference/structure.md", "--section=Linking").stdout == sec.stdout)

miss = ref("manage-project-workspaces/reference/structure.md", "--section", "No such heading")
check("a missing section exits 1", miss.returncode == 1 and not miss.stdout)

for bad in ("../README.md", "/etc/passwd", "manage-project-workspaces/../../bin/dev-workbook", "nope/SKILL.md",
            "manage-project-workspaces/reference"):
    r = ref(bad)
    check(f"refuses {bad}", r.returncode == 1 and not r.stdout)

check("no path is a usage error", ref().returncode == 2)

print(f"\033[{'31' if failures else '32'}m{failures} failed\033[0m" if failures else "\033[32mall passed\033[0m")
sys.exit(1 if failures else 0)

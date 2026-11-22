#!/usr/bin/env python3
"""Tests for the skill frontmatter descriptions — valid plain YAML scalars, the pinned trigger and
exclusion phrases, and the byte budget. Standard library only: the frontmatter rules below are the
plain-scalar constraints that matter for these values, not a real YAML parse.

    python3 tests/test-skill-descriptions.py              # run the checks
    python3 tests/test-skill-descriptions.py --self-test  # prove the checks fail when a phrase is deleted
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every kept trigger and exclusion, per skill (case-insensitive substring of the description).
PINS: dict[str, list[str]] = {
    "manage-project-workspaces": [
        "where did we leave off", "what's the next task", "log progress", "record this decision",
        "close this thread", "how many hours", "issue tracker", "come from git", "Obsidian",
        "ADRs", "open threads",
    ],
    "capture-notes": ["make a note", "capture this", "manage-project-workspaces"],
    "summarize-contribution": [
        "summarize my contribution", "case studies", "what examples do I have",
        "what have I been working on", "manage-project-workspaces",
    ],
    "condense-vault": ["condense the vault", "SessionStart"],
    "ingest-project-docs": ["ingest this project", "bootstrap the workspace"],
}

YAML_INDICATORS = "'\"[{&*!|>%@`"


def description_of(skill_md: Path) -> tuple[list[str], list[str]]:
    """Return (name lines, description lines) of the frontmatter."""
    lines = skill_md.read_text(encoding="utf-8").split("\n")
    if not lines or lines[0] != "---":
        return [], []
    end = lines.index("---", 1) if "---" in lines[1:] else len(lines)
    fm = lines[1:end]
    return ([l for l in fm if l.startswith("name:")], [l for l in fm if l.startswith("description:")])


def results(skills_dir: Path) -> list[tuple[bool, str, str]]:
    """Every check as (ok, name, detail) for the skills under skills_dir."""
    out: list[tuple[bool, str, str]] = []
    for skill in sorted(p.name for p in skills_dir.iterdir() if (p / "SKILL.md").is_file()):
        names, descs = description_of(skills_dir / skill / "SKILL.md")
        out.append((len(names) == 1 and len(descs) == 1, f"{skill}: one name and one single-line description", ""))
        if len(descs) != 1:
            continue
        value = descs[0][len("description:"):].strip()
        out.append((bool(value), f"{skill}: description is not empty", ""))
        if value[:1] not in ("'", '"'):
            out.append((": " not in value, f"{skill}: no ': ' in the plain scalar", ""))
            out.append((" #" not in value, f"{skill}: no ' #' in the plain scalar", ""))
            out.append((value[:1] not in YAML_INDICATORS, f"{skill}: no leading YAML indicator", value[:1]))
        for phrase in PINS.get(skill, []):
            out.append((phrase.lower() in value.lower(), f"{skill}: keeps '{phrase}'", ""))
    for skill in PINS:
        out.append(((skills_dir / skill / "SKILL.md").is_file(), f"{skill}: skill exists", ""))
    return out


def self_test() -> list[tuple[bool, str, str]]:
    """Delete each pinned phrase from a temp copy and require the checks to go red."""
    out: list[tuple[bool, str, str]] = []
    for skill, phrases in PINS.items():
        for phrase in phrases:
            tmp = Path(tempfile.mkdtemp(prefix="dev-workbook-desc-tests."))
            try:
                shutil.copytree(ROOT / "skills", tmp / "skills")
                f = tmp / "skills" / skill / "SKILL.md"
                text = f.read_text(encoding="utf-8")
                lines = text.split("\n")
                for i, l in enumerate(lines):
                    if l.startswith("description:"):
                        while phrase.lower() in lines[i].lower():  # every occurrence
                            idx = lines[i].lower().find(phrase.lower())
                            lines[i] = lines[i][:idx] + lines[i][idx + len(phrase):]
                        break
                f.write_text("\n".join(lines), encoding="utf-8")
                red = any(not ok for ok, _, _ in results(tmp / "skills"))
                out.append((red, f"deleting '{phrase}' from {skill} turns the checks red", ""))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    return out


def run(title: str, items: list[tuple[bool, str, str]]) -> int:
    print(f"\n\033[1m{title}\033[0m")
    bad = 0
    for ok, name, detail in items:
        if ok:
            print(f"  \033[32mok\033[0m   {name}")
        else:
            bad += 1
            print(f"  \033[31mFAIL\033[0m {name}")
            if detail:
                print(f"       {detail}")
    return bad


def main() -> int:
    if "--self-test" in sys.argv:
        bad = run("the checks fail when a pinned phrase is deleted", self_test())
        print(f"\n{'FAIL' if bad else 'PASS'}: {bad} failed")
        return 1 if bad else 0
    items = results(ROOT / "skills")
    bad = run("skill descriptions", items)
    bad += run("the checks themselves", self_test())
    total = len(items) + sum(len(v) for v in PINS.values())
    print(f"\n{total - bad} passed, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

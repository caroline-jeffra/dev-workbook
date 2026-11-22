#!/usr/bin/env python3
"""Tests for the skill frontmatter descriptions — valid plain YAML scalars, the pinned trigger and
exclusion phrases, viewer neutrality, and the byte budget. Standard library only: the frontmatter
rules below are the plain-scalar constraints that matter for these values, not a real YAML parse.

    python3 tests/test-skill-descriptions.py              # run the checks
    python3 tests/test-skill-descriptions.py --self-test  # prove the checks fail on a broken copy
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every quoted trigger and exclusion, per skill (case-insensitive substring of the description).
PINS: dict[str, list[str]] = {
    "manage-project-workspaces": [
        "what's next", "what should I work on", "where did we leave off", "status of <ticket>",
        "log progress", "record this decision", "close this thread", "set up time tracking",
        "how many hours", "issue tracker", "come from git", "ADRs", "open threads",
    ],
    "capture-notes": ["make a note", "capture this", "save this to my vault", "manage-project-workspaces"],
    "summarize-contribution": [
        "summarize my contribution", "write a CV summary", "what did I accomplish", "find me case studies",
        "what examples do I have", "where did we leave off", "what's the status", "what have I been working on",
        "manage-project-workspaces",
    ],
    "condense-vault": ["condense the vault", "clean up the vault", "run the vault cleanup", "SessionStart"],
    "ingest-project-docs": ["starting to track a repo", "ingest this project", "bootstrap the workspace"],
}

# The vault is platform agnostic: descriptions never name a markdown viewer.
NEUTRAL = ["Obsidian", "Foam"]

TOTAL_BUDGET = 2000  # bytes of description across all skills
EACH_BUDGET = 600    # bytes per description

# A plain scalar may not start with any of these (YAML indicator characters).
YAML_INDICATORS = "-?:,[]{}#&*!|>'\"%@`"
# Nor contain these: each ends the scalar or starts a comment.
PLAIN_HAZARDS = [": ", ":\t", " #", "\t#"]
# A top-level frontmatter line: a key, a colon, then a space or nothing.
KEY_LINE = re.compile(r"^[A-Za-z][\w-]*:(?: |$)")

Check = tuple[bool, str, str]


def frontmatter(skill_md: Path) -> tuple[list[str] | None, str]:
    """The frontmatter lines, or (None, reason) when the file has no well-formed frontmatter."""
    raw = skill_md.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return None, "starts with a byte-order mark"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return None, f"is not UTF-8 ({e.reason} at byte {e.start})"
    lines = text.split("\n")
    if lines[0] != "---":
        return None, "does not open with '---'"
    if "---" not in lines[1:]:
        return None, "has no closing '---' line"
    fm = lines[1:lines.index("---", 1)]
    stray = [l for l in fm if l.strip() and l[:1] not in (" ", "\t") and not KEY_LINE.match(l)]
    if stray:
        return None, f"has a line that is not a 'key: value' pair ({stray[0][:30]!r})"
    return fm, ""


def description(fm: list[str]) -> tuple[str | None, list[Check]]:
    """The description value of the frontmatter lines, and the structural checks on it."""
    names = [l for l in fm if l.split(":", 1)[0] == "name"]
    descs = [i for i, l in enumerate(fm) if l.split(":", 1)[0] == "description"]
    checks: list[Check] = [(len(names) == 1, "one name: key", f"{len(names)} found"),
                           (len(descs) == 1, "one description: key", f"{len(descs)} found")]
    if len(descs) != 1:
        return None, checks
    i = descs[0]
    line = fm[i]
    checks.append((line.startswith("description: "), "a space follows 'description:'", line[:20]))
    continued = i + 1 < len(fm) and fm[i + 1][:1] in (" ", "\t") and fm[i + 1].strip() != ""
    checks.append((not continued, "the description is a single line", "an indented continuation line follows"))
    return line[len("description:"):].strip(), checks


def value_checks(value: str) -> list[Check]:
    """The plain-scalar rules, or the quoting rules for a quoted value."""
    if value[:1] in ("'", '"'):
        closed = len(value) >= 2 and value[-1] == value[0]
        return [(closed, "the quoted description is closed", ""),
                (closed and value[1:-1].strip() != "", "the quoted description is not empty", "")]
    out: list[Check] = [(value != "", "the description is not empty", "")]
    out.append((value[:1] not in YAML_INDICATORS, "no leading YAML indicator", value[:1]))
    for hazard in PLAIN_HAZARDS:
        out.append((hazard not in value, f"no {hazard!r} in the plain scalar", ""))
    out.append((not value.endswith(":"), "no trailing ':' in the plain scalar", ""))
    return out


def results(skills_dir: Path) -> list[Check]:
    """Every check as (ok, name, detail) for the skills under skills_dir."""
    out: list[Check] = []
    total = 0
    skills = sorted(p.name for p in skills_dir.iterdir() if (p / "SKILL.md").is_file())
    for skill in skills:
        fm, reason = frontmatter(skills_dir / skill / "SKILL.md")
        out.append((fm is not None, f"{skill}: well-formed frontmatter", reason))
        if fm is None:
            continue
        value, structural = description(fm)
        out += [(ok, f"{skill}: {name}", detail) for ok, name, detail in structural]
        if value is None:
            continue
        out += [(ok, f"{skill}: {name}", detail) for ok, name, detail in value_checks(value)]
        size = len(value.encode("utf-8"))
        total += size
        out.append((size <= EACH_BUDGET, f"{skill}: description is within {EACH_BUDGET} bytes", f"{size} bytes"))
        for viewer in NEUTRAL:
            out.append((viewer.lower() not in value.lower(), f"{skill}: names no viewer ('{viewer}')", ""))
        out.append((skill in PINS, f"{skill}: has pinned phrases", "add it to PINS"))
        for phrase in PINS.get(skill, []):
            out.append((phrase.lower() in value.lower(), f"{skill}: keeps '{phrase}'", ""))
    out.append((total <= TOTAL_BUDGET, f"all descriptions together are within {TOTAL_BUDGET} bytes", f"{total} bytes"))
    for skill, phrases in PINS.items():
        out.append((skill in skills, f"{skill}: skill exists", ""))
        out.append((all(p.strip() for p in phrases), f"{skill}: no empty pinned phrase", ""))
    return out


def edit_description(skill: str, change: Callable[[str], str]) -> Callable[[Path], None]:
    """A mutation that rewrites one skill's description line."""
    def apply(skills_dir: Path) -> None:
        f = skills_dir / skill / "SKILL.md"
        lines = f.read_text(encoding="utf-8").split("\n")
        i = next(k for k, l in enumerate(lines) if l.startswith("description:"))
        lines[i:i + 1] = change(lines[i]).split("\n")
        f.write_text("\n".join(lines), encoding="utf-8")
    return apply


def delete_phrase(phrase: str) -> Callable[[str], str]:
    def change(line: str) -> str:
        while phrase.lower() in line.lower():  # every occurrence
            idx = line.lower().find(phrase.lower())
            line = line[:idx] + line[idx + len(phrase):]
        return line
    return change


def rewrite_file(skill: str, change: Callable[[bytes], bytes]) -> Callable[[Path], None]:
    def apply(skills_dir: Path) -> None:
        f = skills_dir / skill / "SKILL.md"
        f.write_bytes(change(f.read_bytes()))
    return apply


def wrap(line: str) -> str:
    cut = line.rfind(" ", 0, len(line) // 2)
    return line[:cut] + "\n  " + line[cut + 1:]


def unclose(data: bytes) -> bytes:
    head, _, rest = data.partition(b"\n---\n")
    return head + b"\n--- \n" + rest


def body(line: str) -> str:
    return line[len("description: "):]


SAMPLE = "capture-notes"
MUTATIONS: list[tuple[str, Callable[[Path], None]]] = [
    (f"deleting '{phrase}' from {skill}", edit_description(skill, delete_phrase(phrase)))
    for skill, phrases in PINS.items() for phrase in phrases
] + [
    ("wrapping a description onto a continuation line", edit_description(SAMPLE, wrap)),
    ("a ': ' in a plain description", edit_description(SAMPLE, lambda l: l + " Note: more")),
    ("a ' #' in a plain description", edit_description(SAMPLE, lambda l: l + " #tag")),
    ("a trailing ':' on a plain description", edit_description(SAMPLE, lambda l: l + ":")),
    ("a leading '#' on a description", edit_description(SAMPLE, lambda l: "description: #" + body(l))),
    ("a leading '- ' on a description", edit_description(SAMPLE, lambda l: "description: - " + body(l))),
    ("no space after 'description:'", edit_description(SAMPLE, lambda l: "description:" + body(l))),
    ("an empty quoted description", edit_description(SAMPLE, lambda l: 'description: ""')),
    ("an unclosed quoted description", edit_description(SAMPLE, lambda l: 'description: "' + body(l))),
    ("naming a viewer", edit_description(SAMPLE, lambda l: l + " Obsidian")),
    ("a description over budget", edit_description(SAMPLE, lambda l: l + " x" * EACH_BUDGET)),
    ("a closing '--- ' with a trailing space", rewrite_file(SAMPLE, unclose)),
    ("a byte-order mark", rewrite_file(SAMPLE, lambda b: b"\xef\xbb\xbf" + b)),
    ("a non-UTF-8 byte", rewrite_file(SAMPLE, lambda b: b + b"\xff")),
]


def self_test() -> list[Check]:
    """Break a temp copy of skills/ each way and require the checks to go red on it."""
    if any(not ok for ok, _, _ in results(ROOT / "skills")):
        return [(False, "the real skills/ passes before mutating", "fix the failing checks first")]
    out: list[Check] = []
    for label, mutate in MUTATIONS:
        tmp = Path(tempfile.mkdtemp(prefix="dev-workbook-desc-tests."))
        try:
            shutil.copytree(ROOT / "skills", tmp / "skills")
            mutate(tmp / "skills")
            red = any(not ok for ok, _, _ in results(tmp / "skills"))
            out.append((red, f"{label} turns the checks red", ""))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return out


def run(title: str, items: list[Check]) -> int:
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
        bad = run("the checks fail on a broken copy", self_test())
        print(f"\n{'FAIL' if bad else 'PASS'}: {bad} failed")
        return 1 if bad else 0
    bad = run("skill descriptions", results(ROOT / "skills"))
    bad += run("the checks themselves", self_test())
    print(f"\n{'FAIL' if bad else 'PASS'}: {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

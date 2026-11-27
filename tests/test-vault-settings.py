#!/usr/bin/env python3
"""Regression tests for hooks/vault_settings.py — the vault-level `.dev-workbook.json`.

Its `unmanaged` list names top-level vault folders the plugin syncs but never changes. Run directly:

    python3 tests/test-vault-settings.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hooks"))

import vault_settings as vset  # noqa: E402

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


def vault_with(content: str | None) -> Path:
    v = Path(tempfile.mkdtemp())
    if content is not None:
        (v / vset.FILE).write_text(content, encoding="utf-8")
    return v


print("vault_settings")

s = vset.load(vault_with(json.dumps({"unmanaged": ["HouseStyles", "Acme Profiles", "a_b-1"]})))
check(s.unmanaged == ("HouseStyles", "Acme Profiles", "a_b-1") and not s.warnings,
      "a valid list is read in order", repr(s))

s = vset.load(vault_with(None))
check(s.unmanaged == () and not s.warnings, "no file means no unmanaged folders and no warning", repr(s))

s = vset.load(vault_with(json.dumps({})))
check(s.unmanaged == () and not s.warnings, "a file without the key is fine", repr(s))

for label, content in (("not JSON", "{"), ("not an object", "[]"), ("list is not a list", '{"unmanaged": "HouseStyles"}')):
    s = vset.load(vault_with(content))
    check(s.unmanaged == () and len(s.warnings) == 1, f"{label}: empty list and one warning", repr(s))

refused = ["Projects", "projects", "Resources", "Contributions", "Archived", ".obsidian", "a/b", "../x",
           "", " x", "x.md", 7, None, "x\ny", "-x", "a" * 101]
s = vset.load(vault_with(json.dumps({"unmanaged": refused + ["Kept"]})))
check(s.unmanaged == ("Kept",), "reserved, nested, dotted, empty and non-string entries are refused", repr(s.unmanaged))
check(len(s.warnings) == len(refused), "each refused entry gets one warning", f"{len(s.warnings)} warnings")
check(all("\n" not in w for w in s.warnings), "warnings stay on one line")

s = vset.load(vault_with(json.dumps({"unmanaged": ["Acme", "acme", "Acme"]})))
check(s.unmanaged == ("Acme",) and len(s.warnings) == 2, "duplicates (in any letter case) are dropped with a warning",
      repr(s))

v = vault_with(json.dumps({"unmanaged": ["Acme"]}))
(v / "linked.json").write_text(json.dumps({"unmanaged": ["Other"]}), encoding="utf-8")
(v / vset.FILE).unlink()
(v / vset.FILE).symlink_to(v / "linked.json")
s = vset.load(v)
check(s.unmanaged == () and len(s.warnings) == 1, "a symlinked settings file is refused", repr(s))

print("dev-workbook unmanaged")
v = vault_with(json.dumps({"unmanaged": ["HouseStyles", "Projects"]}))
r = subprocess.run([sys.executable, str(ROOT / "bin" / "dev-workbook"), "unmanaged", "--vault", str(v)],
                   capture_output=True, text=True, check=False)
check(r.returncode == 0 and r.stdout == "HouseStyles\n", "prints one valid name per line", repr(r.stdout))
check("Projects" in r.stderr, "warnings go to stderr", repr(r.stderr))
r = subprocess.run([sys.executable, str(ROOT / "bin" / "dev-workbook"), "unmanaged", "--vault", str(vault_with(None))],
                   capture_output=True, text=True, check=False)
check(r.returncode == 0 and r.stdout == "" and r.stderr == "", "prints nothing for a vault without the file",
      repr((r.stdout, r.stderr)))

print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

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

print("names, files and shapes")

v = vault_with(json.dumps({"unmanaged": ["housestyles"]}))
(v / "HouseStyles").mkdir()
check(vset.load(v).unmanaged == ("HouseStyles",), "an entry matches its folder in any letter case and takes its spelling")

s = vset.load(vault_with(json.dumps({"unmanaged": ["Acme ", " Acme", "Acme_", "A"]})))
check(s.unmanaged == ("Acme_", "A") and len(s.warnings) == 2, "leading or trailing spaces are refused", repr(s))

v = vault_with(json.dumps({"unmanaged": ["Linked", "Real"]}))
(v / "Real").mkdir()
(v / "Linked").symlink_to(v / "Real")
s = vset.load(v)
check(s.unmanaged == ("Real",) and any("symlink" in w for w in s.warnings), "a symlinked folder is refused", repr(s))

for label, content in (("deeply nested", "[" * 100000), ("not UTF-8", None)):
    v = vault_with(content)
    if content is None:
        (v / vset.FILE).write_bytes(b'{"unmanaged": ["\xff"]}')
    s = vset.load(v)
    check(s.unmanaged == () and len(s.warnings) == 1, f"{label}: no crash, one warning", repr(s))

v = vault_with(json.dumps({"unmanaged": ["A"], "pad": "x" * (vset.MAX_BYTES + 1)}))
s = vset.load(v)
check(s.unmanaged == () and "KB" in s.warnings[0], "an oversized file is refused", repr(s.warnings))

v = vault_with(None)
(v / vset.FILE).mkdir()
s = vset.load(v)
check(s.unmanaged == () and len(s.warnings) == 1, "a directory in its place is refused", repr(s))

s = vset.load(vault_with(json.dumps({"unmanaged": [f"F{i}" for i in range(vset.MAX_ENTRIES + 5)]})))
check(len(s.unmanaged) == vset.MAX_ENTRIES and len(s.warnings) == 1, "at most MAX_ENTRIES are read", repr(len(s.unmanaged)))


print("approval on this machine")


def git_vault(listed: list[str]) -> Path:
    v = vault_with(json.dumps({"unmanaged": listed}))
    subprocess.run(["git", "init", "-q", str(v)], check=True)
    for name in listed:
        (v / name).mkdir(exist_ok=True)
    return v


v = vault_with(json.dumps({"unmanaged": ["Acme"]}))
s = vset.load(v)
check(s.synced == ("Acme",) and s.pending == (), "outside git, every listed folder counts as approved", repr(s))

v = git_vault(["Acme", "Beta"])
s = vset.load(v)
check(s.unmanaged == ("Acme", "Beta") and s.synced == () and s.pending == ("Acme", "Beta"),
      "in a git vault a listed folder is never changed but not synced until approved", repr(s))
approved, err = vset.approve(v)
check(err is None and approved == ("Acme", "Beta"), "approve records every listed folder", repr((approved, err)))
record = Path(subprocess.run(["git", "-C", str(v), "rev-parse", "--absolute-git-dir"], capture_output=True,
                             text=True, check=True).stdout.strip()) / vset.APPROVED
check(record.read_text() == "acme\nbeta\n", "the approval lives in the vault's .git, not in the synced file")
s = vset.load(v)
check(s.synced == ("Acme", "Beta") and s.pending == (), "approved folders are synced", repr(s))

(v / vset.FILE).write_text(json.dumps({"unmanaged": ["Acme", "Beta", "Private"]}), encoding="utf-8")
(v / "Private").mkdir()
s = vset.load(v)
check(s.synced == ("Acme", "Beta") and s.pending == ("Private",) and "Private" in s.unmanaged,
      "a folder a pull added is never changed but stays unsynced until approved here", repr(s))

(v / vset.FILE).write_text(json.dumps({"unmanaged": ["Beta"]}), encoding="utf-8")
s = vset.load(v)
check(s.synced == ("Beta",), "a folder removed from the list stops syncing without approval", repr(s))

print("approval: safety")

v = git_vault(["Acme", "Beta", "Gamma"])
approved, err = vset.approve(v, ["beta"])
check(err is None and approved == ("Beta",) and vset.load(v).synced == ("Beta",),
      "--approve NAME approves only that folder (in any letter case)", repr((approved, err, vset.load(v))))
approved, err = vset.approve(v, ["Gamma"])
check(vset.load(v).synced == ("Beta", "Gamma"), "approvals add up rather than replace", repr(vset.load(v)))
approved, err = vset.approve(v, ["Nope"])
check(err is not None and "Nope" in err and vset.load(v).synced == ("Beta", "Gamma"),
      "approving a folder that isn't listed is refused and changes nothing", repr(err))
(v / vset.FILE).write_text("{", encoding="utf-8")
approved, err = vset.approve(v)
(v / vset.FILE).write_text(json.dumps({"unmanaged": ["Acme", "Beta", "Gamma"]}), encoding="utf-8")
check(err is not None and vset.load(v).synced == ("Beta", "Gamma"),
      "a malformed settings file refuses approval and keeps earlier approvals", repr(err))
(v / vset.FILE).write_text(json.dumps({"unmanaged": []}), encoding="utf-8")
approved, err = vset.approve(v)
check(err is not None, "approving an empty list is refused", repr(err))
(v / vset.FILE).write_text(json.dumps({"unmanaged": ["Acme", "Beta", "Gamma"]}), encoding="utf-8")

real_git_dir = vset.git_dir
vset._cache.clear()
vset.git_dir = lambda vault: (None, vset.UNKNOWN)
s = vset.load(v)
approved, err = vset.approve(v)
vset.git_dir = real_git_dir
vset._cache.clear()
check(s.synced == () and s.unmanaged == ("Acme", "Beta", "Gamma") and any("git could not" in w for w in s.warnings),
      "a git error (timeout, missing git, refused) syncs nothing — it never counts as outside git", repr(s))
check(err is not None and "nothing was approved" in err, "and approval is refused while git can't be read", repr(err))

main = git_vault(["Acme"])
subprocess.run(["git", "-C", str(main), "-c", "user.email=t@x.invalid", "-c", "user.name=T", "commit", "-q",
                "--allow-empty", "-m", "seed"], check=True)
tree = Path(tempfile.mkdtemp()) / "tree"
subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(tree)], check=True)
(tree / vset.FILE).write_text(json.dumps({"unmanaged": ["Acme"]}), encoding="utf-8")
(tree / "Acme").mkdir()
vset.approve(tree)
check(vset.load(main).synced == ("Acme",), "an approval made in a linked worktree counts in the main checkout",
      repr(vset.load(main)))

check(vset.load(vault_with(None)) == vset.EMPTY, "no settings file: empty, without asking git")

record = Path(subprocess.run(["git", "-C", str(v), "rev-parse", "--absolute-git-dir"], capture_output=True,
                             text=True, check=True).stdout.strip()) / vset.APPROVED
record.unlink()
record.symlink_to(v / "elsewhere")
approved, err = vset.approve(v)
check(err is not None and not (v / "elsewhere").exists(), "approve refuses to write through a symlinked record", repr(err))

print("dev-workbook unmanaged")
CLI = [sys.executable, str(ROOT / "bin" / "dev-workbook"), "unmanaged", "--vault"]
v = git_vault(["HouseStyles", "Projects"])
r = subprocess.run([*CLI, str(v)], capture_output=True, text=True, check=False)
check(r.returncode == 0 and r.stdout == "HouseStyles\tpending approval\n", "lists each folder and its state", repr(r.stdout))
check("Projects" in r.stderr, "warnings go to stderr", repr(r.stderr))
r = subprocess.run([*CLI, str(v), "--approve"], capture_output=True, text=True, check=False)
check(r.returncode == 0 and r.stdout == "HouseStyles\tsynced\n", "--approve syncs them", repr(r.stdout))
r = subprocess.run([*CLI, str(v)], capture_output=True, text=True, check=False)
check(r.stdout == "HouseStyles\tsynced\n", "and the state sticks", repr(r.stdout))
r = subprocess.run([*CLI, str(vault_with(None))], capture_output=True, text=True, check=False)
check(r.returncode == 0 and r.stdout == "" and r.stderr == "", "prints nothing for a vault without the file",
      repr((r.stdout, r.stderr)))
r = subprocess.run([*CLI, str(v), "--bogus"], capture_output=True, text=True, check=False)
check(r.returncode == 2, "an unknown option is refused", repr(r.returncode))
for flag, expect in (("", ""), ("--listed", "HouseStyles\n"), ("--pending", "")):
    r = subprocess.run([sys.executable, str(ROOT / "hooks" / "vault_settings.py"), str(v), *([flag] if flag else [])],
                       capture_output=True, text=True, check=False)
    want = "HouseStyles\n" if flag == "" else expect
    check(r.stdout == want, f"shell entry point {flag or '(synced)'}", repr(r.stdout))

print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

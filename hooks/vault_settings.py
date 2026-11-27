"""Vault-level settings: `<vault>/.dev-workbook.json`.

    {"unmanaged": ["Profiles"]}

`unmanaged` names top-level vault folders that belong to someone else — another plugin, a tool,
you — and that the plugin should **sync but never change**:

- **Never changed** applies to every listed folder at once: no maintenance, no lint, no
  condensing, no renaming or link rewriting, and its notes stay out of duplicate-name checks.
- **Synced** — committed and pushed by the session hooks, staged by background sessions, counted
  as the plugin's own by the first-run consent check — applies only once *this machine* has
  approved the folder (`dev-workbook unmanaged --approve`). The file travels with the vault, so a
  pull can change it; the approval does not travel: it is kept in the vault's `.git`, so a list
  widened elsewhere never makes this machine push a folder it was not asked to. A folder listed
  but not approved is reported at session start. A vault that is not a git repository pushes
  nothing, so there every listed folder counts as approved.

An entry is one folder name at the vault root: letters, digits, space, `_` and `-`, starting and
ending with a letter or digit (or `_`/`-` at the end), at most 100 characters. It is matched to the
folder on disk regardless of letter case and used under the folder's own spelling. Names the plugin
already owns or handles itself (`Projects`, `Resources`, `Contributions`, `Archived`) are refused in
any case, as is a symlinked folder. A refused entry, a malformed, oversized or symlinked file is
reported as a one-line warning and ignored; a missing file just means no unmanaged folders.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

FILE = ".dev-workbook.json"
APPROVED = "dev-workbook-unmanaged"  # in the vault's git directory: names this machine approved
RESERVED = ("Projects", "Resources", "Contributions", "Archived")
NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9 _-]{0,98}[A-Za-z0-9_-])?")
MAX_BYTES = 64 * 1024
MAX_ENTRIES = 100


class Settings(NamedTuple):
    unmanaged: tuple[str, ...]  # every valid listed folder — never changed by the plugin
    synced: tuple[str, ...]     # those this machine approved — committed, pushed, staged
    pending: tuple[str, ...]    # listed but not approved
    warnings: list[str]


EMPTY = Settings((), (), (), [])
_cache: dict[tuple, Settings] = {}
_git_dirs: dict[str, tuple] = {}
NO_GIT = "no-git"     # the vault is positively not inside a git repository
UNKNOWN = "unknown"   # git could not say (timeout, missing, refused): sync nothing


def shown(value: object) -> str:
    """A value as one safe line for a warning."""
    return json.dumps(value, ensure_ascii=True)[:80]


def git_dir(vault: Path) -> tuple[Path | None, str]:
    """(the repository's common git directory, "ok") — or (None, NO_GIT) only when git positively
    says this is not a repository, and (None, UNKNOWN) for any other failure, so that an error
    never counts as "outside git" and turns every listed folder into an approved one.
    The common directory, so a linked worktree and the main checkout share one approval record."""
    key = str(vault.resolve()) if vault.exists() else str(vault)
    if key in _git_dirs:
        return _git_dirs[key]
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    try:
        r = subprocess.run(["git", "-C", str(vault), "rev-parse", "--git-common-dir"],
                           capture_output=True, text=True, timeout=10, env=env, check=False)
    except (OSError, subprocess.SubprocessError):
        return None, UNKNOWN
    out = r.stdout.strip()
    if r.returncode == 0 and out:
        result: tuple = ((vault / out).resolve(), "ok")
    elif r.returncode == 128 and "not a git repository" in r.stderr.lower():
        result = (None, NO_GIT)
    else:
        return None, UNKNOWN
    _git_dirs[key] = result
    return result


def digest(path: Path) -> str:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return "-"
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "?"


def stamp(path: Path) -> tuple:
    try:
        st = path.lstat()
        return (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        return ()


def read_list(path: Path, warnings: list[str]) -> list[object]:
    try:
        if path.is_symlink():
            warnings.append(f"{FILE}: is a symlink; ignored")
            return []
        if not path.is_file():
            if path.exists():
                warnings.append(f"{FILE}: is not a regular file; ignored")
            return []
        if path.stat().st_size > MAX_BYTES:
            warnings.append(f"{FILE}: larger than {MAX_BYTES // 1024} KB; ignored")
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        warnings.append(f"{FILE}: can't be read as JSON ({shown(type(exc).__name__)}); ignored")
        return []
    if not isinstance(data, dict):
        warnings.append(f"{FILE}: must be a JSON object; ignored")
        return []
    entries = data.get("unmanaged", [])
    if not isinstance(entries, list):
        warnings.append(f'{FILE}: "unmanaged" must be a list of folder names; ignored')
        return []
    if len(entries) > MAX_ENTRIES:
        warnings.append(f'{FILE}: "unmanaged" lists more than {MAX_ENTRIES} folders; only the first {MAX_ENTRIES} are read')
    return entries[:MAX_ENTRIES]


def on_disk(vault: Path) -> dict[str, str]:
    """casefolded name -> real name, for the vault's top-level entries."""
    try:
        return {p.name.casefold(): p.name for p in vault.iterdir()}
    except OSError:
        return {}


def read_approved(gd: Path | None) -> set[str]:
    """Casefolded names this machine approved, from the record in the git directory."""
    if gd is None:
        return set()
    try:
        path = gd / APPROVED
        if path.is_symlink() or not path.is_file():
            return set()
        return {line.strip().casefold() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    except (OSError, ValueError):
        return set()


def load(vault: Path | str | None) -> Settings:
    if vault is None:
        return EMPTY
    vault = Path(vault)
    settings_file = vault / FILE
    if not (settings_file.exists() or settings_file.is_symlink()):
        return EMPTY  # the common case: no settings, so no git call at all
    gd, state = git_dir(vault)
    key = (str(vault.resolve()), digest(settings_file), state, digest(gd / APPROVED) if gd else None)
    if key in _cache:
        return _cache[key]
    warnings: list[str] = []
    entries = read_list(vault / FILE, warnings)
    reserved = {r.casefold() for r in RESERVED}
    real = on_disk(vault) if entries else {}
    kept: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not (isinstance(entry, str) and NAME.fullmatch(entry)):
            warnings.append(f'{FILE}: "unmanaged" entry {shown(entry)} is not a top-level folder name; ignored')
            continue
        folded = entry.casefold()
        name = real.get(folded, entry)
        if folded in reserved:
            warnings.append(f'{FILE}: "unmanaged" entry {shown(entry)} is a folder the plugin manages; ignored')
        elif folded in seen:
            warnings.append(f'{FILE}: "unmanaged" entry {shown(entry)} is listed twice; ignored')
        elif (vault / name).is_symlink():
            warnings.append(f'{FILE}: "unmanaged" entry {shown(entry)} is a symlink; ignored')
        else:
            seen.add(folded)
            kept.append(name)
    if state == NO_GIT:
        synced = tuple(kept)  # nothing is pushed outside git, so nothing needs approving
    elif state == UNKNOWN:
        synced = ()  # fail closed: never sync on a git error
        if kept:
            warnings.append(f"{FILE}: git could not read this vault's repository; unmanaged folders are not synced this time")
    else:
        approved = read_approved(gd)
        synced = tuple(n for n in kept if n.casefold() in approved)
    pending = tuple(n for n in kept if n not in synced)
    settings = Settings(tuple(kept), synced, pending, warnings)
    _cache[key] = settings
    return settings


def unmanaged(vault: Path | str | None) -> tuple[str, ...]:
    """Every listed folder: the plugin never changes these."""
    return load(vault).unmanaged


def synced(vault: Path | str | None) -> tuple[str, ...]:
    """Listed folders this machine approved: the hooks commit, push and stage these."""
    return load(vault).synced


def approve(vault: Path | str, names: list[str] | None = None) -> tuple[tuple[str, ...], str | None]:
    """Approve listed folders on this machine — `names` (each must be listed), or every listed one —
    adding to what was approved before. Returns (newly synced names, error)."""
    vault = Path(vault)
    settings = load(vault)
    file_problems = [w for w in settings.warnings if '"unmanaged" entry' not in w and "git could not" not in w]
    if file_problems:
        return (), f"{FILE} has a problem, so nothing was approved: {file_problems[0]}"
    if not settings.unmanaged:
        return (), f"{FILE} lists no unmanaged folders; nothing to approve"
    listed = {n.casefold(): n for n in settings.unmanaged}
    if names:
        unknown = [n for n in names if n.casefold() not in listed]
        if unknown:
            return (), f"not listed in {FILE}: {', '.join(unknown)}"
        chosen = [listed[n.casefold()] for n in names]
    else:
        chosen = list(settings.unmanaged)
    gd, state = git_dir(vault)
    if state == NO_GIT:
        return tuple(chosen), None  # nothing is pushed without git; nothing to record
    if gd is None:
        return (), "git could not read this vault's repository; nothing was approved"
    path = gd / APPROVED
    if path.is_symlink():
        return (), f"{path} is a symlink; refusing to write it"
    keep = sorted(read_approved(gd) | {n.casefold() for n in chosen})
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text("".join(f"{n}\n" for n in keep), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        return (), f"can't write {path} ({exc})"
    _cache.clear()
    return tuple(chosen), None


if __name__ == "__main__":
    # For the shell hooks, one name per line:
    #   vault_settings.py <vault>            folders to sync (listed and approved)
    #   vault_settings.py <vault> --listed   every listed folder (never changed)
    #   vault_settings.py <vault> --pending  listed but not approved on this machine
    import sys

    if len(sys.argv) > 1:
        s = load(sys.argv[1])
        which = sys.argv[2] if len(sys.argv) > 2 else ""
        names = {"--listed": s.unmanaged, "--pending": s.pending}.get(which, s.synced)
        for name in names:
            print(name)

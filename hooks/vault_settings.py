"""Vault-level settings: `<vault>/.dev-workbook.json`.

    {"unmanaged": ["Profiles"]}

`unmanaged` names top-level vault folders that belong to someone else — another plugin, a tool,
you — and that the plugin should **sync but never change**: the session hooks, the spool and the
manual close-out commit and push them, the first-run consent check counts them as the plugin's
own, and nothing else touches them (no maintenance, no lint, no condensing, no renaming, and their
notes stay out of link resolution).

An entry is one folder name at the vault root: letters, digits, space, `_` and `-`, starting with
a letter or digit, at most 100 characters. Names the plugin already owns or handles itself
(`Projects`, `Resources`, `Contributions`, `Archived`) are refused, in any letter case. A refused
entry, a malformed file or a symlinked one is reported as a one-line warning and ignored; a
missing file just means no unmanaged folders.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple

FILE = ".dev-workbook.json"
RESERVED = ("Projects", "Resources", "Contributions", "Archived")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,99}")


class Settings(NamedTuple):
    unmanaged: tuple[str, ...]
    warnings: list[str]


def shown(value: object) -> str:
    """A value as one safe line for a warning."""
    return json.dumps(value, ensure_ascii=True)[:80]


def load(vault: Path | str) -> Settings:
    path = Path(vault) / FILE
    warnings: list[str] = []
    if path.is_symlink():
        return Settings((), [f"{FILE}: is a symlink; ignored"])
    if not path.is_file():
        return Settings((), [])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Settings((), [f"{FILE}: can't be read as JSON ({shown(str(exc))}); ignored"])
    if not isinstance(data, dict):
        return Settings((), [f"{FILE}: must be a JSON object; ignored"])
    entries = data.get("unmanaged", [])
    if not isinstance(entries, list):
        return Settings((), [f'{FILE}: "unmanaged" must be a list of folder names; ignored'])
    reserved = {r.lower() for r in RESERVED}
    kept: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not (isinstance(entry, str) and NAME.fullmatch(entry)):
            warnings.append(f'{FILE}: "unmanaged" entry {shown(entry)} is not a top-level folder name; ignored')
        elif entry.lower() in reserved:
            warnings.append(f'{FILE}: "unmanaged" entry {shown(entry)} is a folder the plugin manages; ignored')
        elif entry.lower() in seen:
            warnings.append(f'{FILE}: "unmanaged" entry {shown(entry)} is listed twice; ignored')
        else:
            seen.add(entry.lower())
            kept.append(entry)
    return Settings(tuple(kept), warnings)


def unmanaged(vault: Path | str | None) -> tuple[str, ...]:
    return load(vault).unmanaged if vault is not None else ()


if __name__ == "__main__":
    # `python3 vault_settings.py <vault>` — the unmanaged folders, one per line (for the shell hooks).
    import sys

    for name in unmanaged(sys.argv[1]) if len(sys.argv) > 1 else ():
        print(name)

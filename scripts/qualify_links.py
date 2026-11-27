#!/usr/bin/env python3
"""Qualify every ambiguous wikilink in a workspace with the path of the note it means.

Used by `condense-vault` to fix `ambiguous-link` findings. Log dates and structural files
(`Overview`, `ProgressLog`, the indexes) repeat in every workspace by design, so a bare
`[[2026-10-01]]` or `[[Overview]]` names several notes. Obsidian binds it to one of them by its own
tie-break, which is often another project's; Foam and other viewers refuse to pick. Either way the
link is not saying what its author meant.

    qualify_links.py [--vault PATH] [--dry-run]

What it does, for every note inside a workspace (a folder with `.vault-config.json`):

  * A link whose target names more than one note is resolved against the workspace the linking
    note lives in, as its author meant it. When exactly one candidate is in that workspace, the
    target is replaced with the shortest path that names only that note:
    `[[2026-10-01]]` -> `[[Alpha/Log/2026-10-01|2026-10-01]]`.
  * The text the link displayed is kept as an alias, so the note reads the same; an existing alias
    or `#heading` is preserved. Inside a table row no alias is added — an alias pipe splits the
    row in viewers that ignore the `\\|` escape — so a cell gets the bare qualified path.
  * Links in code spans and fenced blocks, embeds, and anything outside a workspace or in
    `Archived/` are left alone. A link with no candidate, or several, in its own workspace is
    reported and left alone — that one needs a person.

Concurrent callers share rename_note.py's lock, so a rename and a qualify never interleave.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "hooks"))

from dev_workbook_paths import resolve_vault  # noqa: E402
from vault_maintain import WIKILINK, VaultNames, find_workspaces, shortest_ref, write_atomic  # noqa: E402

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def candidates(names: VaultNames, target: str) -> list[str]:
    t = target.strip("/").lower()
    return sorted(p for p in names.paths if p.lower() == t or p.lower().endswith("/" + t))


def qualify_text(text: str, ws_rel: str, names: VaultNames) -> tuple[str, int, list[str]]:
    """Returns (new text, links qualified, ambiguous targets left as they were)."""
    fixed, left = 0, []

    def sub(m: re.Match, in_table: bool) -> str:
        nonlocal fixed
        embed, inner = m.group(1), m.group(2)
        if embed:
            return m.group(0)
        split = re.search(r"\\?\||#", inner)
        target = (inner[: split.start()] if split else inner).strip()
        rest = inner[split.start():] if split else ""
        if not target or names.matches(target) <= 1:
            return m.group(0)
        home = [c for c in candidates(names, target) if c.startswith(ws_rel + "/")]
        if len(home) != 1:
            left.append(target)
            return m.group(0)
        ref = shortest_ref(home[0], names.suffixes)
        if not in_table and (not rest or rest.startswith("#")):
            # Keep what the reader saw: `[[2026-10-01]]` still displays `2026-10-01`.
            rest = rest + "|" + target + rest
        fixed += 1
        return f"[[{ref}{rest}]]"

    out, fence = [], None
    for line in text.split("\n"):
        m = FENCE.match(line)
        if m:
            if fence is None:
                fence = m.group(1)[0]
            elif m.group(1)[0] == fence:
                fence = None
            out.append(line)
            continue
        if fence is not None:
            out.append(line)
            continue
        in_table = line.lstrip().startswith("|")
        # Odd-numbered pieces between backticks are code spans: leave them as written.
        pieces = line.split("`")
        for i in range(0, len(pieces), 2):
            pieces[i] = WIKILINK.sub(lambda mm: sub(mm, in_table), pieces[i])
        out.append("`".join(pieces))
    return "\n".join(out), fixed, left


def qualify(vault: Path, dry_run: bool = False) -> tuple[int, int, list[str]]:
    """Returns (links qualified, files changed, `path: target` lines needing a person)."""
    names = VaultNames.scan(vault)
    links = files = 0
    unresolved: list[str] = []
    workspaces = sorted(find_workspaces(vault), key=lambda w: len(w.parts), reverse=True)
    seen: set[Path] = set()
    for ws in workspaces:                      # deepest first, so a nested workspace owns its notes
        ws_rel = ws.relative_to(vault).as_posix()
        if ws_rel == "." or ws_rel.split("/")[0] == "Archived":
            continue
        for p in sorted(ws.rglob("*.md")):
            rel = p.relative_to(vault)
            if p in seen or p.is_symlink() or any(x.startswith(".") for x in rel.parts):
                continue
            seen.add(p)
            text = p.read_text(encoding="utf-8")
            out, fixed, left = qualify_text(text, ws_rel, names)
            unresolved += [f"{rel.as_posix()}: [[{t}]]" for t in sorted(set(left))]
            if fixed:
                links += fixed
                files += 1
                if not dry_run:
                    write_atomic(p, out)
    return links, files, unresolved


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    vault = resolve_vault(a.vault)
    if vault is None or not vault.is_dir():
        print(f"qualify_links: vault not found: {vault}", file=sys.stderr)
        return 2
    vault = vault.resolve()
    key = hashlib.sha1(str(vault).encode()).hexdigest()[:12]
    # O_NOFOLLOW and no truncation: a planted symlink must not turn opening the lock into a write.
    fd = os.open(Path(tempfile.gettempdir()) / f"dev-workbook-rename-{key}.lock",
                 os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        links, files, unresolved = qualify(vault, a.dry_run)
    for line in unresolved:
        print(f"unresolved: {line} — no single note of that name in this workspace")
    verb = "would qualify" if a.dry_run else "qualified"
    print(f"{verb} {links} link(s) in {files} file(s); {len(unresolved)} left for a person")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Rename or move one vault note and rewrite every reference to it, vault-wide.

Used by `condense-vault` to fix `bad-name`, `legacy-name`, `dup-name` and `root-stray` findings.
Renaming a note by hand leaves every [[link]] to it broken, and a rename that rewrites only links
leaves `supersedes:` frontmatter pointing at a name that no longer exists. This does both.

    rename_note.py [--vault PATH] [--dry-run] "<old vault-relative path>" "<new vault-relative path>"

What it rewrites, in every note outside `Archived/`, dot-directories and folders listed as
unmanaged in the vault's .dev-workbook.json:

  * `[[Old]]`, `[[Old|alias]]`, `[[Old\\|alias]]` (inside a table), `[[Old#heading]]`, and the
    path-qualified forms `[[Folder/Old` that point at the renamed note — in any letter case and
    with or without a `.md` suffix, since viewers resolve `[[old.md]]` to the same note.
  * `supersedes:` / `superseded_by:` frontmatter naming the note — scalar, inline list or block list.

Two rules keep it from rewriting links that meant a different note:

  * A link is rewritten only when it names the renamed note: its target is the end of that note's
    path (`[[Old]]`, `[[Log/Old]]`, `[[Alpha/Log/Old]]`), or its path is the note's folder or
    workspace (`[[Alpha/Old]]`).
  * If that target also names another note, the link is rewritten only inside the renamed note's
    own workspace (`Projects/<name>/`); elsewhere it may mean the other one.

Every rewritten link uses the shortest path that names the moved note and no other — bare when the
new name is unique, `[[Alpha/Log/2026-10-01]]` when it is not.

The file is moved with `git mv` when git tracks it, a plain move otherwise. Concurrent callers
are serialised with a lock, so parallel runs never interleave read-modify-write on one note.
Fails closed: a missing source or an existing target changes nothing, and neither does a path that
leaves the vault (absolute, `..`, a dot-directory, or through a symlink) — git stores symlinks, so
one can arrive with a pull and must not turn a rename into a move out of, or into, the vault. The
note is moved before any link is rewritten, so a failed move leaves every note as it was.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import vault_settings  # noqa: E402
from dev_workbook_paths import resolve_vault  # noqa: E402
from vault_maintain import shortest_ref, suffix_counts, write_atomic  # noqa: E402

SUPERSESSION_KEYS = ("supersedes", "superseded_by")


def is_versioned(vault: Path) -> bool:
    r = subprocess.run(["git", "-C", str(vault), "rev-parse", "--is-inside-work-tree"],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def is_tracked(vault: Path, rel: str) -> bool:
    """`git mv` refuses an untracked file — after the links are already rewritten — so check first."""
    r = subprocess.run(["git", "-C", str(vault), "ls-files", "--error-unmatch", "--", rel],
                       capture_output=True, text=True)
    return r.returncode == 0


def notes(vault: Path):
    """Every note whose links a rename may rewrite — never one in a folder listed as unmanaged."""
    skip = ("Archived", *vault_settings.unmanaged(vault))
    for p in vault.rglob("*.md"):
        rel = p.relative_to(vault)
        if any(part.startswith(".") for part in rel.parts) or rel.parts[0] in skip:
            continue
        if p.is_symlink():
            continue
        yield p, rel


def workspace_of(rel: Path) -> Path | None:
    return Path(*rel.parts[:2]) if rel.parts[0] == "Projects" and len(rel.parts) > 2 else None


def rewrite_supersession(text: str, old: str, new: str) -> str:
    """Rewrite the old name inside supersedes/superseded_by values, in any YAML list shape."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return text
    lines, key = m.group(1).split("\n"), None
    token = re.compile(r"(?<![\w-])" + re.escape(old) + r"(?![\w-])")
    for i, line in enumerate(lines):
        km = re.match(r"^([A-Za-z_][\w-]*):(.*)$", line)
        if km:
            key = km.group(1)
            if key in SUPERSESSION_KEYS:
                lines[i] = f"{key}:" + token.sub(new, km.group(2))
        elif key in SUPERSESSION_KEYS and re.match(r"^\s*-\s", line):
            lines[i] = token.sub(new, line)
    return "---\n" + "\n".join(lines) + "\n---\n" + text[m.end():]


def in_vault(vault: Path, rel: str) -> Path:
    """vault/rel, or ValueError when rel could leave the vault: absolute, `..`, a dot-directory,
    or any existing part of it a symlink."""
    p = Path(rel)
    if not rel or p.is_absolute() or any(part in ("", ".", "..") or part.startswith(".")
                                         for part in p.parts):
        raise ValueError(f"not a path inside the vault: {rel}")
    cur = vault
    for part in p.parts:
        cur = cur / part
        if cur.is_symlink():
            raise ValueError(f"refusing a path through a symlink: {rel}")
    return cur


def rename(vault: Path, old: str, new: str, dry_run: bool = False) -> tuple[int, int]:
    """Returns (links rewritten, files changed). Raises ValueError on a refused rename."""
    src, dst = in_vault(vault, old), in_vault(vault, new)
    if not src.is_file():
        raise ValueError(f"no such note: {old}")
    if src.suffix != ".md":
        raise ValueError(f"only a .md note can be renamed: {old}")
    if dst.exists():
        raise ValueError(f"target already exists: {new}")
    if dst.suffix != ".md":
        raise ValueError(f"target must be a .md file: {new}")

    old_name, new_name = src.stem, dst.stem
    rel = Path(old)
    ws = workspace_of(rel)
    # By name, not rglob(src.name): a name holding `[`, `*` or `?` is a glob pattern to rglob.
    shared = any(p != src and p.name == src.name for p in vault.rglob("*.md")
                 if not any(x.startswith(".") for x in p.relative_to(vault).parts))

    # Every note the vault's links can resolve to — Archived/ included, since links still reach it.
    paths = {
        r.with_suffix("").as_posix()
        for r in (p.relative_to(vault) for p in vault.rglob("*.md"))
        if not any(x.startswith(".") for x in r.parts)
    }
    old_rel, new_rel = rel.with_suffix("").as_posix(), Path(new).with_suffix("").as_posix()
    new_ref = shortest_ref(new_rel, suffix_counts((paths - {old_rel}) | {new_rel}))

    def named_by(target: str) -> list[str]:
        t = target.lower()
        return [p for p in paths if p.lower() == t or p.lower().endswith("/" + t)]

    # Path prefixes that can only mean this note: its own folder, and its workspace root.
    folders = [str(rel.parent)] + ([str(ws)] if ws else [])
    prefixes = set()
    for f in folders:
        if f and f != ".":
            prefixes.add((f + "/").lower())
            prefixes.add((f.replace("Projects/", "", 1) + "/").lower())

    link = re.compile(
        r"\[\[((?:[^\[\]|#\n]*/)?)" + re.escape(old_name) + r"(?:\.md)?(?=\]\]|\||\\\||#)",
        re.IGNORECASE,
    )
    links = files = 0
    pending: list[tuple[Path, str]] = []
    for p, r in notes(vault):
        in_ws = ws is not None and r.is_relative_to(ws)
        text = p.read_text(encoding="utf-8")

        def sub(m: re.Match) -> str:
            nonlocal links
            pre = m.group(1)
            if pre.lower() not in prefixes:
                # Resolve the link the way a viewer does: by the end of the note's path. A
                # `[[Log/x]]` written in another workspace means that workspace's log, not this one.
                hits = named_by(pre + old_name)
                if old_rel not in hits or (len(hits) > 1 and not in_ws):
                    return m.group(0)
            links += 1
            return "[[" + new_ref

        out = link.sub(sub, text)
        if not shared or in_ws:
            out = rewrite_supersession(out, old_name, new_name)
        if out != text:
            files += 1
            pending.append((p, out))

    if dry_run:
        return links, files
    # Move first: if it fails, no note has been touched. The renamed note's own rewrite (a link to
    # itself) then goes to its new path.
    dst.parent.mkdir(parents=True, exist_ok=True)
    if is_versioned(vault) and is_tracked(vault, old):
        r = subprocess.run(["git", "-C", str(vault), "mv", "--", old, new], capture_output=True, text=True)
        if r.returncode != 0:
            raise ValueError(f"git mv failed: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else r.returncode}")
    else:
        src.rename(dst)
    for p, out in pending:
        write_atomic(dst if p == src else p, out)
    return links, files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vault")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("old")
    ap.add_argument("new")
    a = ap.parse_args(argv)

    vault = resolve_vault(a.vault)
    if vault is None or not vault.is_dir():
        print(f"rename_note: vault not found: {vault}", file=sys.stderr)
        return 2
    vault = vault.resolve()
    key = hashlib.sha1(str(vault).encode()).hexdigest()[:12]
    # O_NOFOLLOW and no truncation: in a shared temp dir, a planted symlink must not turn
    # opening the lock into clobbering whatever it points at.
    fd = os.open(Path(tempfile.gettempdir()) / f"dev-workbook-rename-{key}.lock",
                 os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            links, files = rename(vault, a.old, a.new, a.dry_run)
        except ValueError as exc:
            print(f"rename_note: {exc}", file=sys.stderr)
            return 1
    verb = "would rewrite" if a.dry_run else "rewrote"
    print(f"{a.old} -> {a.new}: {verb} {links} link(s) in {files} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

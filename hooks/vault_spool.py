#!/usr/bin/env python3
"""Spooled vault writes for background sessions — stage now, merge in once the session is over.

Claude Code refuses `Write`/`Edit` on a git checkout from a background session until it isolates
itself in a worktree, and the vault is a git checkout. Lifting that guard would let a background
session overwrite edits the user or another session made meanwhile. Instead a background session
writes its notes to a spool outside the vault, and the session hooks merge the spool in once the
session that wrote it is over:

    dev-workbook stage Projects/Alpha/Log/2026-11-05.md
      → copies the note (if it exists) into the spool twice: once as the base, once to edit,
        and prints the path to edit

    session-end.sh (the session's own exit) and vault-pull.sh (any later start)
      → for every spool whose session is over: a note unchanged in the vault since it was staged
        is replaced; one changed meanwhile is merged three ways (git merge-file); one whose
        edits do not merge stays in the spool, and the next session start reports where.

Layout, under ${XDG_STATE_HOME:-~/.local/state}/dev-workbook/spool/<session id>/:

    meta.json        {"vault", "session", "pid", "created"}; "held": true once a conflict is kept
    notes/<path>     the copy the session edits — its vault-relative path, unchanged
    base/<path>      the note as it was when staged; absent if the note did not exist then

Only the paths the session-end hook commits are accepted (vault-push.sh's is_owned_path), and only
notes and workspace configs, so a spool can never smuggle a file the hooks would not publish.
Nothing here deletes or renames a vault note.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath

OWNED_DIRS = ("Projects", "Resources", "Contributions")
OWNED_FILES = ("Home.md", "TasksArchive.md", "WorkPlanning.md")

# A spool with no recorded owner process is treated as finished once it has been idle this long.
ORPHAN_AFTER = 6 * 3600

# Append-shaped notes: a log gains entries at the end, the progress log a line at the top. When two
# sessions both add to one, a plain three-way merge calls the adjacent insertions a conflict; keeping
# both sides (--union) is right as long as the conflict is in the body, not the frontmatter.
APPEND_NOTE = re.compile(r"(^|/)Log/[^/]+\.md$|(^|/)ProgressLog\.md$")


def spool_root() -> Path:
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".local" / "state") / "dev-workbook" / "spool"


def session_id() -> str | None:
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    return sid if sid and re.fullmatch(r"[A-Za-z0-9._-]+", sid) else None


def check_path(rel: str) -> str | None:
    """The normalised vault-relative path, or None if the spool must not carry it."""
    p = PurePosixPath(rel.replace("\\", "/"))
    if p.is_absolute() or not p.parts or any(part in ("", ".", "..") for part in p.parts):
        return None
    name = p.name
    if not (name.endswith(".md") or name == ".vault-config.json"):
        return None
    if len(p.parts) == 1:
        return str(p) if name in OWNED_FILES else None
    return str(p) if p.parts[0] in OWNED_DIRS else None


def inside(vault: Path, rel: str) -> Path | None:
    """The note's vault path, or None if a symlink would take it outside the vault."""
    target = (vault / rel).resolve()
    try:
        target.relative_to(vault.resolve())
    except ValueError:
        return None
    return target


def read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def load_meta(spool: Path) -> dict:
    try:
        meta = json.loads((spool / "meta.json").read_text(encoding="utf-8"))
        return meta if isinstance(meta, dict) else {}
    except (OSError, ValueError):
        return {}


def save_meta(spool: Path, meta: dict) -> None:
    (spool / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- stage


def stage(vault: Path, rel: str, sid: str | None = None) -> tuple[Path | None, str]:
    """Stage one note for this session; return (path to edit, message)."""
    norm = check_path(rel)
    if norm is None:
        return None, (f"'{rel}' is not a path the vault hooks publish — stage notes under "
                      f"{', '.join(OWNED_DIRS)}/ or {', '.join(OWNED_FILES)}")
    if inside(vault, norm) is None:
        return None, f"'{rel}' resolves outside the vault"
    sid = sid or session_id()
    if not sid:
        return None, "no session id (CLAUDE_CODE_SESSION_ID is unset); cannot tell whose spool this is"

    spool = spool_root() / sid
    work, base = spool / "notes" / norm, spool / "base" / norm
    spool.mkdir(parents=True, exist_ok=True)
    meta = load_meta(spool)
    if not meta:
        save_meta(spool, {"vault": str(vault.resolve()), "session": sid,
                          "pid": os.environ.get("CLAUDE_PID", "").strip() or None,
                          "created": time.strftime("%Y-%m-%dT%H:%M:%S")})
    elif meta.get("vault") != str(vault.resolve()):
        return None, f"this session's spool belongs to another vault ({meta.get('vault')})"

    # Staging twice keeps the first base: re-reading the vault now would hide a concurrent edit.
    if work.exists() or base.exists():
        return work, "already staged"
    work.parent.mkdir(parents=True, exist_ok=True)
    current = vault / norm
    if current.is_file():
        base.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(current, base)
        shutil.copyfile(current, work)
        return work, "staged"
    return work, "new note — create it at this path"


# ---------------------------------------------------------------- apply


def pid_alive(pid: object) -> bool:
    try:
        os.kill(int(pid), 0)  # type: ignore[arg-type]
    except (TypeError, ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def last_touched(spool: Path) -> float:
    newest = 0.0
    for p in spool.rglob("*"):
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    return newest


def finished(spool: Path, meta: dict, ending: str | None) -> bool:
    """True once the session that owns the spool can write to it no more."""
    if ending and meta.get("session") == ending:
        return True
    if meta.get("pid"):
        return not pid_alive(meta["pid"])
    return time.time() - last_touched(spool) > ORPHAN_AFTER


def busy(vault: Path) -> str | None:
    """A git operation in progress in the vault, which a working-tree write would corrupt."""
    for state, what in (("MERGE_HEAD", "a merge"), ("rebase-merge", "a rebase"),
                        ("rebase-apply", "a rebase"), ("CHERRY_PICK_HEAD", "a cherry-pick"),
                        ("REVERT_HEAD", "a revert")):
        try:
            r = subprocess.run(["git", "-C", str(vault), "rev-parse", "--git-path", state],
                               capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode == 0 and r.stdout.strip():
            p = Path(r.stdout.strip())
            if (p if p.is_absolute() else vault / p).exists():
                return what
    return None


def frontmatter_lines(text: bytes) -> int:
    """How many leading lines are frontmatter (0 if none)."""
    lines = text.split(b"\n")
    if not lines or lines[0].rstrip(b"\r") != b"---":
        return 0
    for i, line in enumerate(lines[1:], 1):
        if line.rstrip(b"\r") == b"---":
            return i + 1
    return 0


def merge(rel: str, current: bytes, base: bytes, ours: bytes) -> bytes | None:
    """Three-way merge of the session's edit into the vault's current note; None on conflict."""
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for name, data in (("current", current), ("base", base), ("staged", ours)):
            f = Path(tmp) / name
            f.write_bytes(data)
            files.append(str(f))

        def run(*flags: str) -> subprocess.CompletedProcess | None:
            try:
                return subprocess.run(["git", "merge-file", "-p", *flags, *files],
                                      capture_output=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                return None

        r = run()
        if r is None or r.returncode < 0:
            return None
        if r.returncode == 0:
            return r.stdout
        if not APPEND_NOTE.search(rel):
            return None
        # Union only when every conflict sits below the frontmatter, so both sides' entries are kept
        # but a key is never written twice.
        fm = frontmatter_lines(r.stdout)
        if frontmatter_lines(base) and not fm:
            return None                        # the conflict swallowed the opening ---
        if any(line.startswith(b"<<<<<<< ") for line in r.stdout.split(b"\n")[:fm]):
            return None
        u = run("--union")
        return u.stdout if u is not None and u.returncode == 0 else None


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".devwb-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def apply_note(vault: Path, rel: str, work: Path, base_file: Path) -> str:
    """Merge one staged note in. Returns 'applied', 'unchanged', 'conflict' or 'refused'."""
    if check_path(rel) is None:
        return "refused"
    target = inside(vault, rel)
    if target is None:
        return "refused"
    ours = read_bytes(work)
    if ours is None:
        return "refused"
    base = read_bytes(base_file)
    current = read_bytes(target) if target.is_file() else None

    if base is not None and ours == base:
        return "unchanged"                     # staged, never edited
    if current == ours:
        return "unchanged"                     # the vault already says the same
    if base is None:
        if current is not None:
            return "conflict"                  # created here and, meanwhile, in the vault
        result = ours
    elif current is None:
        return "conflict"                      # edited here, deleted in the vault
    elif current == base:
        result = ours                          # untouched in the vault: plain replace
    else:
        merged = merge(rel, current, base, ours)
        if merged is None:
            return "conflict"
        result = merged

    # Last look before writing: an interactive session may have saved since we read it.
    if (read_bytes(target) if target.is_file() else None) != current:
        return "conflict"
    write_atomic(target, result)
    return "applied"


def apply_spool(vault: Path, spool: Path, meta: dict) -> list[str]:
    sid = str(meta.get("session") or spool.name)
    short = sid[:8]
    notes_dir, base_dir = spool / "notes", spool / "base"
    applied, conflicts, refused = [], [], []
    for work in sorted(p for p in notes_dir.rglob("*") if p.is_file()) if notes_dir.is_dir() else []:
        rel = work.relative_to(notes_dir).as_posix()
        outcome = apply_note(vault, rel, work, base_dir / rel)
        if outcome == "applied":
            applied.append(rel)
        elif outcome == "conflict":
            conflicts.append(rel)
            continue
        elif outcome == "refused":
            refused.append(rel)
            continue
        work.unlink(missing_ok=True)
        (base_dir / rel).unlink(missing_ok=True)

    msgs = []
    if applied:
        msgs.append(f"applied {len(applied)} note(s) from background session {short}: {' '.join(applied)}")
    if refused:
        msgs.append(f"background session {short}: not applying {len(refused)} path(s) the vault "
                    f"hooks do not publish: {' '.join(refused)}")
    if conflicts or refused:
        # Kept for the user to merge by hand. Report once, not at every session start.
        if not meta.get("held"):
            meta["held"] = True
            save_meta(spool, meta)
        if conflicts:
            msgs.append(f"background session {short}: {len(conflicts)} note(s) changed in the vault "
                        f"since they were staged and do not merge: {' '.join(conflicts)}. Its versions "
                        f"are kept in {notes_dir}; merge them by hand, then delete {spool}.")
    else:
        shutil.rmtree(spool, ignore_errors=True)
    return msgs


def apply(vault: Path, ending: str | None = None) -> list[str]:
    """Merge every finished spool for this vault in. Returns lines worth reporting."""
    root = spool_root()
    if not root.is_dir() or not vault.is_dir():
        return []
    vault_key = str(vault.resolve())
    due = []
    for spool in sorted(p for p in root.iterdir() if p.is_dir()):
        meta = load_meta(spool)
        if meta.get("vault") != vault_key or meta.get("held"):
            continue
        if finished(spool, meta, ending):
            due.append((spool, meta))
    if not due:
        return []
    what = busy(vault)
    if what:
        return [f"vault has {what} in progress — {len(due)} background session spool(s) left "
                f"unapplied until it is finished."]
    msgs = []
    for spool, meta in due:
        msgs.extend(apply_spool(vault, spool, meta))
    return msgs


def pending(vault: Path) -> list[str]:
    """One line per spool for this vault: session, state and the notes it holds."""
    root = spool_root()
    if not root.is_dir():
        return []
    vault_key = str(vault.resolve())
    lines = []
    for spool in sorted(p for p in root.iterdir() if p.is_dir()):
        meta = load_meta(spool)
        if meta.get("vault") != vault_key:
            continue
        notes = spool / "notes"
        rels = sorted(p.relative_to(notes).as_posix() for p in notes.rglob("*") if p.is_file()) \
            if notes.is_dir() else []
        state = "held (conflict)" if meta.get("held") else (
            "running" if not finished(spool, meta, None) else "due")
        lines.append(f"{spool.name} [{state}] {spool}: {' '.join(rels) or '(nothing written)'}")
    return lines


def main(argv: list[str] | None = None) -> int:
    """vault_spool.py stage VAULT PATH | apply VAULT [SESSION] | list VAULT"""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2 or args[0] not in ("stage", "apply", "list"):
        print(main.__doc__, file=sys.stderr)
        return 2
    cmd, vault = args[0], Path(args[1])
    if cmd == "stage":
        if len(args) != 3:
            print(main.__doc__, file=sys.stderr)
            return 2
        path, msg = stage(vault, args[2])
        if path is None:
            print(f"dev-workbook: {msg}", file=sys.stderr)
            return 1
        print(path)
        print(f"dev-workbook: {msg}", file=sys.stderr)
        return 0
    try:
        out = apply(vault, args[2] if len(args) > 2 else None) if cmd == "apply" else pending(vault)
    except Exception as exc:                   # a hook must never break the session
        out = [f"background session spool not applied: {exc}"] if cmd == "apply" else []
    for line in out:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

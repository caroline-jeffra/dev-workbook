#!/usr/bin/env python3
"""Print, on one line, the facts every dev-workbook skill needs before it touches the vault.

    workspace_context.py [--vault PATH] [--repo PATH]

One line of space-separated `key=value`, every key always present, `-` for none. A value that
contains whitespace, `"`, `=` or a control character is JSON-quoted, so a hostile filename or index
cell cannot break the line. Exits 0 always; an unexpected exception still prints every key (the
unknown ones `-`) plus `error=<short>`.

    vault, vault_ok          the resolved vault, and whether it is an existing directory
    vault_from               arg | env | config | legacy-config | legacy | default — which tier said so
    code_root, code_root_from  where repos live, and which config tier said so
    repo                     the git toplevel of --repo / the working directory
    index, index_notes       the workspace index (vault-relative), and whether prose follows its table
    match                    path | basename | moved | ambiguous | unmatched | misconfigured | new
                             | no-index | no-vault — how the repo maps to a row of the index
    workspace, indexed, candidates, structured, trial   details of that match
    consent                  ask | ok — whether the vault holds notes this plugin did not put there
    sync                     hooks | self | none — who commits and pushes the vault
    background               yes | no — a background session (CLAUDE_JOB_DIR set)

Read-only: nothing here writes to the vault.
"""

from __future__ import annotations

import json
import unicodedata
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import dev_workbook_paths as paths  # noqa: E402

KEYS = ("vault", "vault_ok", "vault_from", "code_root", "code_root_from", "repo", "index", "index_notes", "match",
        "workspace", "indexed", "candidates", "structured", "trial", "consent", "sync", "background",
        "error")
INDEXES = ("Projects/WorkspaceIndex.md", "Projects/_index.md")
ARCHIVES = ("TasksArchive.md", "Tasks Archive.md")
PLUGIN_DIRS = ("Projects", "Resources", "Contributions", "HouseStyles", "Archived")
VERSION_FILES = (".dev-workbook-version", ".claudesidion-version")
HEARTBEAT = "dev-workbook-hooks"
HEARTBEAT_MAX_AGE = 24 * 3600


# --- output ----------------------------------------------------------------------------------

def fmt(value: object) -> str:
    """One value, quoted as JSON unless it is plain printable ASCII with no space, quote or `=`.
    Anything else — a separator, an invisible or bidi control, a look-alike `＝` — could make a
    value read as more keys than it is, so it is quoted, and JSON escapes it to plain text."""
    s = "-" if value is None or value == "" else str(value)
    if any(c in '"=' or not ("!" <= c <= "~") for c in s):
        # Readable characters stay readable (a vault path may hold an accent); only control,
        # format and separator characters are escaped.
        return "".join(f"\\u{ord(c):04x}" if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp")
                       and c not in "\n\t" else c
                       for c in json.dumps(s, ensure_ascii=False))
    return s


def render(out: dict[str, str]) -> str:
    return " ".join(f"{k}={fmt(out.get(k))}" for k in KEYS)


# --- index parsing ---------------------------------------------------------------------------

class Row(NamedTuple):
    path: str        # first cell, backticks stripped
    workspace: str   # Projects/<Name>


WIKILINK = re.compile(r"\[\[([^\[\]\n]*)\]\]")    # no `[` inside: a run of `[` stays linear
SEPARATOR = re.compile(r"^:?-+:?$")
TRIAL_HEADING = re.compile(r"^##\s+trial workspaces\b", re.I)
# A workspace name is one folder under Projects/. Skills splice it into shell commands and paths,
# so anything beyond word characters, dots, dashes and spaces (or a `..`) is not a workspace.
SAFE_NAME = re.compile(r"\w[\w. -]*\Z")


def workspace_of(cells_text: str) -> str | None:
    """The last `…/Overview` wikilink in the text, as `Projects/<Name>`."""
    found = None
    for m in WIKILINK.finditer(cells_text):
        target = re.split(r"\\?\|", m.group(1))[0].split("#")[0].strip()
        if target.lower().endswith(".md"):
            target = target[:-3]
        if target.lower().endswith("/overview"):
            name = target[: -len("/overview")].strip("/")
            if name.startswith("Projects/"):
                name = name[len("Projects/"):]
            found = f"Projects/{name}" if SAFE_NAME.fullmatch(name) and ".." not in name else None
    return found


def parse_row(line: str) -> Row | None:
    body = line.strip()[1:]
    parts = re.split(r"(?<!\\)\|", body, maxsplit=1)
    path = parts[0].strip().strip("`").strip()
    ws = workspace_of(parts[1] if len(parts) > 1 else "")
    return Row(path, ws) if ws else None


def is_placeholder(path: str) -> bool:
    return path == "" or path[0] in "_(*"


def first_table(lines: list[str], start: int, stop: int) -> tuple[list[Row], int, int, int]:
    """Rows of the first table in lines[start:stop], the span [begin, end) it covers, and how many
    of its data rows could not be read (no safe `…/Overview` link)."""
    i = start
    while i < stop and not lines[i].lstrip().startswith("|"):
        i += 1
    begin = i
    while i < stop and lines[i].lstrip().startswith("|"):
        i += 1
    rows, unread = [], 0
    for line in lines[begin + 1:i]:                     # the first line is the header
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if all(SEPARATOR.match(c) for c in cells if c) and any(cells):
            continue
        row = parse_row(line)
        if row:
            rows.append(row)
        else:
            unread += 1
    return rows, begin, i, unread


def parse_index(text: str) -> tuple[list[Row], list[Row], bool, bool]:
    """(main rows, trial rows, whether prose follows the main table, whether the index has rows
    this parser could not read — a row without a usable link, or a table it could not place)."""
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    for i in range(start, len(lines)):
        if lines[i].startswith("# "):
            start = i + 1
            break
    trial_at = next((i for i in range(start, len(lines)) if TRIAL_HEADING.match(lines[i])), len(lines))
    main, begin, end, unread = first_table(lines, start, trial_at)
    notes = begin < end and any(l.strip() for l in lines[end:trial_at])
    trial = first_table(lines, trial_at + 1, len(lines))[0] if trial_at < len(lines) else []
    # No main table, yet a table somewhere (say the trial section sits above it): the index has a
    # shape this parser does not know, and reading it as empty would scaffold a duplicate.
    if begin == end and any(l.lstrip().startswith("|") for l in lines[start:]):
        unread += 1
    return [r for r in main if not is_placeholder(r.path)], \
        [r for r in trial if not is_placeholder(r.path)], notes, unread > 0


# --- matching --------------------------------------------------------------------------------

def norm_path(p: str | os.PathLike) -> str:
    return unicodedata.normalize("NFC", os.path.normcase(os.path.realpath(p)))


def name_key(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFC", s).lower() if c.isalnum())


def resolve_row(path: str, code_root: str) -> str:
    return path if os.path.isabs(path) else os.path.join(code_root, path)


def locate(rows: list[Row], cands: list[str], code_root: str) -> tuple[str, list[Row]]:
    """How the repo (its candidate checkouts) maps onto rows: (kind, matching rows)."""
    cand_norm = [norm_path(c) for c in cands]
    for c in cand_norm:
        hit = [r for r in rows if norm_path(resolve_row(r.path, code_root)) == c]
        if hit:
            return "path", hit
    keys = {name_key(os.path.basename(c.rstrip("/"))) for c in cands} - {""}
    hit = [r for r in rows
           if name_key(os.path.basename(r.path.rstrip("/"))) in keys
           or name_key(r.workspace.rsplit("/", 1)[-1]) in keys]
    if not hit:
        return "none", []
    if len({r.workspace for r in hit}) > 1:
        return "ambiguous", hit
    moved = not os.path.exists(resolve_row(hit[0].path, code_root))
    return ("moved" if moved else "basename"), hit


def classify(rows: list[Row], cands: list[str], code_root: str, unread: bool = False) -> dict[str, str]:
    kind, hit = locate(rows, cands, code_root)
    # Every row missing at once means the code root is wrong, not that this repo moved: rewriting a
    # row against a wrong root would corrupt it. A lone row cannot tell the two apart, so it stays
    # `moved` and the skill confirms before touching it.
    total_miss = not any(os.path.exists(resolve_row(r.path, code_root)) for r in rows)
    if kind in ("moved", "ambiguous") and len(rows) >= 2 and total_miss:
        return {"match": "misconfigured"}
    if kind in ("path", "basename"):
        return {"match": kind, "workspace": hit[0].workspace}
    if kind == "moved":
        return {"match": kind, "workspace": hit[0].workspace, "indexed": hit[0].path}
    if kind == "ambiguous":
        return {"match": kind, "candidates": ",".join(sorted({r.workspace for r in hit}))}
    if unread:
        return {"match": "unmatched"}       # rows we could not read may be this repo's: ask
    if not rows:
        return {"match": "new"}
    if total_miss:
        return {"match": "misconfigured"}
    return {"match": "unmatched"}


# --- git and filesystem facts ----------------------------------------------------------------

def git(cwd: str, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def repo_checkouts(start: str) -> tuple[str, list[str]]:
    """The repo's toplevel, and every checkout to match: it and, for a linked worktree, the main one."""
    start = os.path.abspath(start)
    top = git(start, "rev-parse", "--show-toplevel") if os.path.isdir(start) else None
    if not top:
        return start, [start]
    cands = [top]
    common = git(start, "rev-parse", "--git-common-dir")
    if common:
        common = os.path.normpath(common if os.path.isabs(common) else os.path.join(start, common))
        if os.path.basename(common) == ".git":
            main = os.path.dirname(common)
            if norm_path(main) != norm_path(top):
                cands.append(main)
    return top, cands


def consent_for(vault: Path) -> str:
    if any((vault / n).exists() for n in INDEXES + ARCHIVES):
        return "ok"
    projects = vault / "Projects"
    if projects.is_dir() and not any((projects / v).exists() for v in VERSION_FILES):
        return "ask"
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d != ".git" and not (root == str(vault) and d in PLUGIN_DIRS)]
        if any(f.endswith(".md") for f in files):
            return "ask"
    return "ok"


def sync_mode(vault: Path) -> str:
    if not vault.is_dir() or git(str(vault), "rev-parse", "--is-inside-work-tree") != "true":
        return "none"
    git_dir = git(str(vault), "rev-parse", "--absolute-git-dir")
    if git_dir:
        try:
            if time.time() - os.stat(os.path.join(git_dir, HEARTBEAT)).st_mtime < HEARTBEAT_MAX_AGE:
                return "hooks"
        except OSError:
            pass
    return "self"


def read_index(vault: Path) -> tuple[str | None, str]:
    for rel in INDEXES:
        try:
            return rel, (vault / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return None, ""


# --- the command -----------------------------------------------------------------------------

def gather(out: dict[str, str], explicit_vault: str | None, repo_arg: str | None) -> None:
    vault = Path(os.path.abspath(paths.resolve_vault(explicit_vault)))
    out["vault"] = str(vault)
    out["vault_ok"] = "yes" if vault.is_dir() else "no"
    out["vault_from"] = "arg" if explicit_vault else paths.vault_source()
    out["background"] = "yes" if os.environ.get("CLAUDE_JOB_DIR", "") else "no"
    code_root = str(os.path.abspath(paths.resolve_code_root()))
    out["code_root"] = code_root
    out["code_root_from"] = paths.code_root_source()
    top, cands = repo_checkouts(repo_arg or os.getcwd())
    out["repo"] = top
    out["consent"] = consent_for(vault)
    out["sync"] = sync_mode(vault)
    if not vault.is_dir():
        out["match"] = "no-vault"
        return
    rel, text = read_index(vault)
    if rel is None:
        out["match"] = "no-index"
        return
    out["index"] = rel
    main, trial, notes, unread = parse_index(text)
    out["index_notes"] = "yes" if notes else "no"
    out.update(classify(main, cands, code_root, unread))
    t_kind, t_hit = locate(trial, cands, code_root)
    if t_kind in ("path", "basename", "moved"):
        out["trial"] = t_hit[0].workspace
    if out.get("workspace", "-") != "-":
        out["structured"] = "yes" if (vault / out["workspace"] / ".vault-config.json").is_file() else "no"


def parse_args(argv: list[str]) -> tuple[str | None, str | None]:
    vault = repo = None
    it = iter(argv)
    for a in it:
        if a == "--vault":
            vault = next(it, None)
        elif a.startswith("--vault="):
            vault = a.split("=", 1)[1]
        elif a == "--repo":
            repo = next(it, None)
        elif a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        else:
            raise ValueError(f"unknown argument {a}")
    return vault, repo


def main(argv: list[str]) -> int:
    out = {k: "-" for k in KEYS}
    try:
        vault, repo = parse_args(argv)
        gather(out, vault, repo)
    except Exception as e:  # noqa: BLE001 — the line must always print
        out["error"] = f"{type(e).__name__}: {e}"[:80]
    print(render(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

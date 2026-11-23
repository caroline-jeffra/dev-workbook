#!/usr/bin/env python3
"""Do the mechanical part of a close-out in one call: the day's log, the ProgressLog line and the
TasksArchive row.

    workspace_closeout.py [--vault PATH] [--repo PATH] [--workspace Projects/<Name>] [--commit] [--dry-run]

The clauses arrive as JSON on stdin, never as shell arguments, so backticks, `$` and apostrophes
in them are never run or mangled by a shell:

    {"date": "2026-11-23", "headline": "...", "did": ["..."], "decided": [], "learned": [],
     "case_study": [], "links": [], "archive": "...", "project": "dev-workbook"}

`date` (the day the session started) and `headline` are required; `archive` is the day's terse
TasksArchive clause, `project` the alias for this workspace's link in a month's projects line.

    Log/<date>.md     created in the templates/log.md layout, or merged: each clause is appended to
                      its line unless the line already holds it as a whole clause, a missing line
                      is inserted in template order, nothing else (and no frontmatter) is touched
    ProgressLog.md    the day's line, newest first; a same-day line is replaced
    TasksArchive.md   the day's row (and the year, month and project link it needs), fitted to the
                      file as it is: padded cells, kebab-case aliases, unsorted months

Each file keeps its line endings (LF or CRLF) and a leading BOM. A target reached through a symlink
inside the vault, or resolving outside it, is refused.

It never prints vault text: one line per file, `<path> created|merged|unchanged`, with clause
counts. A background session stages each file (vault_spool) instead of writing the vault, and
refuses rather than write it directly. `--dry-run` writes nothing (in a background session it reads
the staged copies that exist). `--commit`, with sync=self and outside a background session, also
refreshes the indexes and runs hooks/vault-push.sh, and ends with
`commit=<sha>|none|failed pushed=yes|no|no-remote`: `failed` when this run changed a file and the
hook made no commit (its reason is printed above).

A workspace found only by repo name (match=basename: another checkout holds the indexed path) is
refused before any write, in every sync mode: confirm it, then pass it as `--workspace`.

Exit 0 when done; 3 with a one-line reason, before any write, when it refuses. The reason starts
with `input:` (the request is malformed: fix it and rerun) or `workspace:` / `archive:` (the vault
is not in a state this command writes).
"""

from __future__ import annotations

import contextlib
import datetime
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import vault_maintain  # noqa: E402
import vault_spool  # noqa: E402
import workspace_brief  # noqa: E402
import workspace_context as wc  # noqa: E402

FIELDS = {"date", "headline", "did", "decided", "learned", "case_study", "links", "archive", "project"}
LISTS = ("did", "decided", "learned", "case_study", "links")
LABELS = ("Did", "Decided", "Learned", "Case study", "Links")      # template order
SEP = {"Did": "; ", "Learned": "; ", "Decided": ", ", "Links": ", "}
FIELD_OF = {"Did": "did", "Decided": "decided", "Learned": "learned", "Case study": "case_study", "Links": "links"}
LABEL_LINE = re.compile(r"^- \*\*(Did|Decided|Learned|Case study|Links):\*\*(.*)$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# C0 and C1 controls except tab (NEL included), DEL, the line and paragraph separators, and the bidi
# marks, embeddings, overrides and isolates.
CONTROL = re.compile("[\x00-\x08\x0a-\x1f\x7f-\x9f\u061c\u200e\u200f\u2028-\u202e\u2066-\u2069]")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
YEAR_HEAD = re.compile(r"^# (\d{4})\s*$")
BOM = "\ufeff"
MONTH_HEAD = re.compile(r"^## ([A-Z][a-z]{2}) (\d{4})\s*$")
ROW = re.compile(r"^\|\s*(\d+)\s*\|")
PROJECTS_HEAD = "### Month's Projects"
MAX_STDIN = 1_000_000
HEADLINE_WORDS = 12

PROGRESS_NEW = """---
type: log-index
status: reference
---

# Progress log — {project}

One line per working day. Detail lives in the dated note.
"""


class Refusal(Exception):
    """Something that makes the close-out unsafe or meaningless; nothing has been written. `kind` is
    `input` for a malformed request, `workspace` or `archive` for a vault this command cannot write."""

    def __init__(self, message: str, kind: str = "workspace") -> None:
        super().__init__(message)
        self.kind = kind


def norm(s: str) -> str:
    return s.replace("**", "").casefold().strip()


def holds(line: str, clause: str, sep: str) -> bool:
    """Whether `line`, split on `sep`, already holds `clause` as whole clauses (case-folded, bold
    stripped). A clause that itself contains `sep` must match that many neighbouring clauses."""
    have = [norm(c) for c in line.split(sep)]
    want = [norm(c) for c in clause.split(sep)]
    return any(have[i:i + len(want)] == want for i in range(len(have) - len(want) + 1))


# --- the request -----------------------------------------------------------------------------

def one_line(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Refusal(f"{what} must be a non-empty string", "input")
    if CONTROL.search(value):
        raise Refusal(f"{what} must be one line without control, separator or bidi characters", "input")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise Refusal(f"{what} is not valid text", "input") from None
    return value.strip()


def parse_request(raw: str) -> dict:
    try:
        req = json.loads(raw)
    except ValueError:
        raise Refusal("stdin is not JSON", "input") from None
    if not isinstance(req, dict):
        raise Refusal("stdin must be a JSON object", "input")
    unknown = sorted(set(req) - FIELDS)
    if unknown:
        raise Refusal(f"unknown field {unknown[0]}", "input")
    date = one_line(req.get("date"), "date")
    try:
        if not DATE.match(date):
            raise ValueError
        datetime.date.fromisoformat(date)
    except ValueError:
        raise Refusal("date must be a real YYYY-MM-DD date", "input") from None
    out = {"date": date, "headline": one_line(req.get("headline"), "headline")}
    if len(out["headline"].split()) > HEADLINE_WORDS:
        print(f"closeout: headline is over {HEADLINE_WORDS} words", file=sys.stderr)
    for key in LISTS:
        items = req.get(key, [])
        if not isinstance(items, list):
            raise Refusal(f"{key} must be a list of strings", "input")
        out[key] = [one_line(i, key) for i in items]
    archive = req.get("archive")
    out["archive"] = one_line(archive, "archive") if archive not in (None, "") else None
    if out["archive"] and ("|" in out["archive"] or "[[" in out["archive"]):
        raise Refusal("archive must not contain | or [[ (no links or pipes in table cells)", "input")
    project = req.get("project")
    out["project"] = one_line(project, "project") if project not in (None, "") else None
    if out["project"] and not wc.SAFE_NAME.match(out["project"]):
        raise Refusal("project must be a plain name", "input")
    return out


# --- the day's log ---------------------------------------------------------------------------

def insert_at(lines: list[str], label: str) -> int:
    """Where a new `label` line goes: after the last line of its own or an earlier kind, else before
    the first of a later kind, else right after the `# <date>` heading block, else after the last
    non-blank line."""
    rank = LABELS.index(label)
    after, before = -1, None
    for i, ln in enumerate(lines):
        m = LABEL_LINE.match(ln)
        if not m:
            continue
        if LABELS.index(m.group(1)) <= rank:
            after = i
        elif before is None:
            before = i
    if after >= 0:
        return after + 1
    if before is not None:
        return before
    start = 0
    if lines and lines[0].strip() == "---":     # skip the frontmatter, whose `# ` lines are comments
        start = next((i + 1 for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
    head = next((i for i in range(start, len(lines)) if lines[i].startswith("# ")), None)
    if head is not None:
        end = head
        while end + 1 < len(lines) and lines[end + 1].strip() and not lines[end + 1].startswith("#"):
            end += 1
        if end + 1 >= len(lines) or lines[end + 1].strip():
            lines.insert(end + 1, "")
        pos = end + 2                            # one blank line after the block
        if pos >= len(lines):
            lines.append("")
        elif lines[pos].strip():
            lines.insert(pos, "")                # and one before whatever follows
        return pos
    end = max((i for i, ln in enumerate(lines) if ln.strip()), default=-1)
    if end >= 0 and not lines[end].startswith("- "):
        lines.insert(end + 1, "")
        end += 1
    return end + 1


def merge_log(old: str | None, date: str, req: dict) -> tuple[str, dict[str, int]]:
    lines = (old if old is not None else f"---\ntype: log\ndate: {date}\n---\n\n# {date}\n").split("\n")
    counts = {"skipped": 0}
    for label in LABELS:
        key = FIELD_OF[label]
        clauses = req[key]
        if label == "Case study":
            for c in clauses:
                line = f"- **Case study:** {c}"
                if line in (ln.strip() for ln in lines):
                    counts["skipped"] += 1
                    continue
                lines.insert(insert_at(lines, label), line)
                counts[key] = counts.get(key, 0) + 1
            continue
        idx = next((i for i, ln in enumerate(lines) if (m := LABEL_LINE.match(ln)) and m.group(1) == label), None)
        current = LABEL_LINE.match(lines[idx]).group(2).strip() if idx is not None else ""
        added = 0
        for c in clauses:
            if holds(current, c, SEP[label]):
                counts["skipped"] += 1
                continue
            current = f"{current}{SEP[label]}{c}" if current else c
            added += 1
        if not added:
            continue
        if idx is None:
            lines.insert(insert_at(lines, label), f"- **{label}:** {current}")
        else:
            lines[idx] = f"- **{label}:** {current}"
        counts[key] = added
    return "\n".join(lines), counts


# --- ProgressLog -----------------------------------------------------------------------------

def merge_progress(old: str | None, name: str, date: str, headline: str) -> str:
    entry = f"- **[[{name}/Log/{date}|{date}]]** — {headline}"
    lines = (old if old is not None else PROGRESS_NEW.format(project=name)).split("\n")
    lead = re.compile(r"^- (?:\*\*)?\[\[(?:[^\]|]*/)?Log/" + date + r"[|\]]|^- \*\*" + date + r"\*\*")
    same = next((i for i, ln in enumerate(lines) if lead.match(ln)), None)   # the bullet's leading link or date
    if same is not None:
        lines[same] = entry
        return "\n".join(lines)
    bullets = []
    for i, ln in enumerate(lines):
        m = re.match(r"^- .*?(\d{4}-\d{2}-\d{2})", ln)
        if m:
            bullets.append((i, m.group(1)))
    older = next((i for i, d in bullets if d < date), None)
    if older is not None:
        lines.insert(older, entry)
    elif bullets:
        lines.insert(bullets[-1][0] + 1, entry)
    else:
        end = max((i for i, ln in enumerate(lines) if ln.strip()), default=-1)
        lines[end + 1:end + 1] = ["", entry]
    return "\n".join(lines)


# --- TasksArchive ----------------------------------------------------------------------------

def find_alias(text: str, name: str) -> str | None:
    m = re.search(r"\[\[(?:Projects/)?" + re.escape(name) + r"/Overview\|([^\]|]+)\]\]", text)
    return m.group(1) if m else None


def new_month(mon: str, year: int, link: str, day: int, clause: str) -> list[str]:
    return [f"## {mon} {year}", "", PROJECTS_HEAD, link, "", "| Date | Tasks |", "| ---- | ----- |",
            f"| {str(day).ljust(4)} | {clause} |"]


def year_range(lines: list[str], year: int) -> tuple[int, int] | None:
    for i, ln in enumerate(lines):
        m = YEAR_HEAD.match(ln)
        if m and int(m.group(1)) == year:
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("# ")), len(lines))
            return i, end
    return None


def month_range(lines: list[str], ys: int, ye: int, mon: str, year: int) -> tuple[int, int] | None:
    for i in range(ys + 1, ye):
        m = MONTH_HEAD.match(lines[i])
        if m and (m.group(1), int(m.group(2))) == (mon, year):
            end = next((j for j in range(i + 1, ye) if lines[j].startswith(("## ", "# "))), ye)
            return i, end
    return None


def merge_archive(old: str, d: datetime.date, name: str, project: str | None, clause: str) -> tuple[str, list[str]]:
    alias = project or find_alias(old, name) or name
    link = f"[[{name}/Overview|{alias}]]"
    mon, detail = MONTHS[d.month - 1], []
    lines = old.split("\n")
    yr = year_range(lines, d.year)
    if yr is None:                       # newest first: above the first older year, else after the last
        block = [f"# {d.year}", "", *new_month(mon, d.year, link, d.day, clause)]
        older = next((i for i, ln in enumerate(lines)
                      if (m := YEAR_HEAD.match(ln)) and int(m.group(1)) < d.year), None)
        if older is not None:
            lines[older:older] = [*block, ""]
        else:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ["", *block, ""]
        return "\n".join(lines), ["year=+1", "month=+1", "link=+1", "row=new"]
    ys, ye = yr
    mr = month_range(lines, ys, ye, mon, d.year)
    if mr is None:
        block = new_month(mon, d.year, link, d.day, clause)
        older = next((i for i in range(ys + 1, ye)
                      if (m := MONTH_HEAD.match(lines[i])) and m.group(1) in MONTHS     # `## Okt 2026` is no month
                      and (int(m.group(2)), MONTHS.index(m.group(1))) < (d.year, d.month - 1)),
                     None)
        if older is not None:
            lines[older:older] = [*block, ""]
        else:
            pos = ye
            while pos > ys + 1 and not lines[pos - 1].strip():
                pos -= 1
            lines[pos:pos] = ["", *block]
        return "\n".join(lines), ["month=+1", "link=+1", "row=new"]

    ms, me = mr
    # the project link
    ph = next((i for i in range(ms + 1, me) if lines[i].strip() == PROJECTS_HEAD), None)
    if ph is None:
        lines[ms + 1:ms + 1] = ["", PROJECTS_HEAD, link]
        detail.append("link=+1")
    else:
        stop = next((i for i in range(ph + 1, me) if lines[i].startswith(("|", "#"))), me)
        area = range(ph + 1, stop)
        target = re.compile(r"\[\[(?:Projects/)?" + re.escape(name) + r"/Overview[|\]#\\]")
        if not any(target.search(lines[i]) for i in area):
            last = next((i for i in reversed(area) if lines[i].strip()), None)
            if last is None:
                lines.insert(ph + 1, link)
            else:
                lines[last] = f"{lines[last].rstrip()}, {link}"
            detail.append("link=+1")
    ys, ye = year_range(lines, d.year)
    ms, me = month_range(lines, ys, ye, mon, d.year)

    # the day's row
    head = next((i for i in range(ms + 1, me) if re.match(r"^\|\s*Date\s*\|", lines[i])), None)
    if head is None:
        pos = me
        while pos > ms + 1 and not lines[pos - 1].strip():
            pos -= 1
        lines[pos:pos] = ["", "| Date | Tasks |", "| ---- | ----- |", f"| {str(d.day).ljust(4)} | {clause} |"]
        return "\n".join(lines), [*detail, "row=new"]
    if head + 1 >= me or not re.match(r"^\|[\s:|-]+\|\s*$", lines[head + 1]):
        raise Refusal("the month's table in TasksArchive.md has no header separator", "archive")
    first_cell = lines[head + 1].strip().strip("|").split("|")[0].strip()
    width = max(len(first_cell), len(str(d.day)))
    rows = []
    i = head + 2
    while i < me and lines[i].startswith("|"):
        m = ROW.match(lines[i])
        if m:
            rows.append((i, int(m.group(1))))
        i += 1
    same = next((i for i, day in rows if day == d.day), None)
    if same is not None:
        m = re.match(r"^(\|[^|]*\|)(.*)$", lines[same])
        cell = m.group(2).rstrip()
        cell = cell[:-1] if cell.endswith("|") else cell
        if holds(cell, clause, ", "):
            return "\n".join(lines), [*detail, "row=unchanged"]
        lines[same] = f"{m.group(1)} {cell.strip()}, {clause} |"
        return "\n".join(lines), [*detail, "row=extended"]
    entry = f"| {str(d.day).ljust(width)} | {clause} |"
    days = [day for _i, day in rows]
    if all(a >= b for a, b in zip(days, days[1:])):
        older = next((i for i, day in rows if day < d.day), None)
        lines.insert(older if older is not None else (rows[-1][0] + 1 if rows else head + 2), entry)
    else:
        print(f"closeout: the {mon} {d.year} rows of TasksArchive.md are not in day order; "
              "the new row went to the top", file=sys.stderr)
        lines.insert(head + 2, entry)
    return "\n".join(lines), [*detail, "row=new"]


# --- the plan --------------------------------------------------------------------------------

def read_text(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return path.read_bytes().decode("utf-8", errors="surrogateescape")


def split_text(old: str | None) -> tuple[str | None, str, str]:
    """(the text with LF line endings and no BOM, the file's line ending, its BOM or "")."""
    if old is None:
        return None, "\n", ""
    bom = BOM if old.startswith(BOM) else ""
    body = old[len(bom):]
    eol = "\r\n" if "\r\n" in body else "\n"
    return body.replace("\r\n", "\n"), eol, bom


def through_link(vault: Path, rel: str) -> bool:
    """Whether any component of `rel` below the vault is a symlink (the vault itself may be one)."""
    p = vault
    for part in PurePosixPath(rel).parts:
        p = p / part
        if p.is_symlink():
            return True
    return False


def staged_copy(vault: Path, rel: str) -> Path | None:
    """This background session's staged copy of `rel` if it has one; never stages anything."""
    sid, checked = vault_spool.session_id(), vault_spool.check_path(rel)
    if not sid or not checked:
        return None
    spool = vault_spool.spool_root() / sid
    if vault_spool.load_meta(spool).get("vault") != str(vault.resolve()):
        return None
    work = spool / "notes" / checked
    return work if work.is_file() else None


def describe(counts: dict[str, int]) -> list[str]:
    order = ("did", "decided", "learned", "case_study", "links")
    return [f"{k}=+{counts[k]}" for k in order if counts.get(k)] + ([f"skipped={counts['skipped']}"] if counts["skipped"] else [])


def plan(vault: Path, workspace: str, req: dict, background: bool, dry_run: bool) -> list[tuple[str, Path, str | None, str, list[str]]]:
    """(rel, path to write, old text, new text, detail) for each file this close-out touches."""
    name, date = workspace[len("Projects/"):], req["date"]
    rels = [f"{workspace}/Log/{date}.md", f"{workspace}/ProgressLog.md"]
    if req["archive"]:
        if not (vault / "TasksArchive.md").is_file():
            if (vault / "Tasks Archive.md").is_file():
                raise Refusal("only the legacy Tasks Archive.md exists and closeout does not write it; rename it "
                              "TasksArchive.md (condense-vault's reconcile pass does) and rerun", "archive")
            raise Refusal("TasksArchive.md is missing; scaffold it first (scaffold.md)", "archive")
        rels.append("TasksArchive.md")
    paths = {}
    for rel in rels:
        real = vault_spool.inside(vault, rel)
        if real is None:
            raise Refusal(f"{rel} resolves outside the vault")
        if through_link(vault, rel):
            raise Refusal(f"{rel} is reached through a symlink inside the vault")
        paths[rel] = real
    if background:
        for rel in rels:
            if dry_run:                          # read what the session has staged, stage nothing new
                paths[rel] = staged_copy(vault, rel) or paths[rel]
                continue
            work, why = vault_spool.stage(vault, rel)
            if work is None:
                raise Refusal(f"cannot stage {rel}: {why}")
            paths[rel] = work
    out = []
    for rel in rels:
        old = read_text(paths[rel])
        text, eol, bom = split_text(old)         # merged as LF text, written back as the file was
        detail: list[str] = []
        if rel.endswith(f"/Log/{date}.md"):
            new, counts = merge_log(text, date, req)
            detail = describe(counts)
        elif rel.endswith("/ProgressLog.md"):
            new = merge_progress(text, name, date, req["headline"])
        else:
            new, detail = merge_archive(text or "", datetime.date.fromisoformat(date), name, req["project"], req["archive"])
        if old is not None:
            new = old if new == text else bom + new.replace("\n", eol)
        out.append((rel, paths[rel], old, new, detail))
    return out


# --- --commit --------------------------------------------------------------------------------

def head_of(vault: Path) -> str | None:
    return wc.git(str(vault), "rev-parse", "HEAD")


def commit(vault: Path, out: dict[str, str], changed: bool) -> list[str]:
    if out["background"] == "yes":
        return ["commit=none background=yes"]
    if out["sync"] != "self":
        return [f"commit=none sync={out['sync']}"]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            vault_maintain.main([str(vault)])
        except Exception:  # noqa: BLE001 — the commit goes ahead on whatever maintain managed
            pass
    before = head_of(vault)
    lines = []
    try:
        r = subprocess.run(["bash", str(HOOKS / "vault-push.sh")], capture_output=True, text=True, timeout=120,
                           env={**os.environ, "DEVWB_VAULT": str(vault), "DEVWB_NO_RELAY": "1"})
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.TimeoutExpired) as e:
        lines = [f"dev-workbook: the push hook did not finish: {type(e).__name__}"]
    after = head_of(vault)
    moved = bool(after) and after != before
    sha = wc.git(str(vault), "rev-parse", "--short", "HEAD") if moved else None
    if not wc.git(str(vault), "remote"):
        pushed = "no-remote"
    elif changed and not moved:              # the hook declined: this run's files are in no commit
        pushed = "no"
    else:
        pushed = "yes" if wc.git(str(vault), "rev-list", "--count", "@{u}..HEAD") == "0" else "no"
    return [*lines, f"commit={sha or ('failed' if changed else 'none')} pushed={pushed}"]


# --- the command -----------------------------------------------------------------------------

def parse_args(argv: list[str]) -> dict:
    opts = {"vault": None, "repo": None, "workspace": None, "commit": False, "dry_run": False}
    it = iter(argv)
    for a in it:
        flag, eq, value = a.partition("=")
        if flag in ("--vault", "--repo", "--workspace"):
            opts[flag[2:]] = value if eq else next(it, None)
        elif a == "--commit":
            opts["commit"] = True
        elif a == "--dry-run":
            opts["dry_run"] = True
        else:
            raise Refusal(f"unknown argument {a}", "input")
    return opts


def run(argv: list[str]) -> list[str]:
    opts = parse_args(argv)
    raw = sys.stdin.read(MAX_STDIN + 1)
    if len(raw) > MAX_STDIN:
        raise Refusal("stdin is too large", "input")
    req = parse_request(raw)
    out: dict[str, str] = {}
    try:
        workspace = workspace_brief.locate(out, opts["vault"], opts["repo"], opts["workspace"])
    except ValueError as e:
        raise Refusal(str(e)) from None
    if workspace is None:
        raise Refusal(f"no structured workspace for this repo (match={out.get('match', '-')}); pass --workspace")
    if out.get("match") == "basename":      # maybe another repo's workspace: never write on a guess
        raise Refusal(f"{workspace} was found only by repo name (match=basename); confirm it, then pass --workspace {workspace}")
    vault = Path(out["vault"])
    background = out["background"] == "yes"
    steps = plan(vault, workspace, req, background, opts["dry_run"])
    lines, changed = [], False
    for rel, path, old, new, detail in steps:
        status = "created" if old is None else ("unchanged" if new == old else "merged")
        changed = changed or status != "unchanged"
        if status != "unchanged" and not opts["dry_run"]:
            vault_spool.write_atomic(path, new.encode("utf-8", errors="surrogateescape"))
        lines.append(" ".join([rel if " " not in rel else json.dumps(rel), status, *detail,
                               *(["dry-run"] if opts["dry_run"] else [])]))
    if opts["commit"]:
        lines += ["commit=none dry-run"] if opts["dry_run"] else commit(vault, out, changed)
    return lines


def main(argv: list[str]) -> int:
    try:
        lines = run(argv)
    except Refusal as e:
        print(f"closeout: {e.kind}: {e}", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"closeout: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

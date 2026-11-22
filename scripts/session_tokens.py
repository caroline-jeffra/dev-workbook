#!/usr/bin/env python3
"""Measure what dev-workbook costs in real sessions, from Claude Code session transcripts.

Read-only. It prints sizes, counts, dates, skill names and versions, and never any transcript
text. Used to track the plugin's footprint across releases: figures are grouped by the plugin
version the session loaded, and every figure carries its session count `n`.

The method, kept stable so figures stay comparable over time:

  * Only `user`, `assistant` and `attachment` records are read, line by line. `api-request*`
    records are skipped unread: they repeat tool results.
  * Every record is counted once across the whole run, by its ID (tool-call ID, tool-result
    `tool_use_id`, `message.id`, record `uuid`), so resumed sessions and subagents that copy
    earlier records add nothing. Subagent files fold into their parent session.
  * "In context" bytes are the bytes the transcript holds. A large tool result is stored in a
    file and the transcript keeps only a short preview, which is what reached the model.
  * Bytes are attributed by text size. Token usage is reported only as per-session totals (it
    counts the whole context on every turn), and is for context, not attribution.
  * A session counts only if it has dev-workbook activity: a skill load or a vault call.
    Sessions run from inside the vault are left out, since every file operation there would
    look like a vault call.
  * Hook context is the SessionStart `hook_additional_context` total for ALL plugins: the
    record names only the event, so this plugin's share cannot be separated out.
  * "est. tokens" is plugin bytes (skills + descriptions + re-injection + reference reads)
    divided by 4.

Usage:
    session_tokens.py [--repo PATH] [--transcripts DIR ...] [--vault P] [--since YYYY-MM-DD]
                      [--sessions N] [--by session|version] [--json]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dev_workbook_paths as paths  # noqa: E402
from session_hours import PROJECTS, transcript_dirs  # noqa: E402

KEPT = ("user", "assistant", "attachment")
# The cache is plugins/cache/<marketplace>/<plugin>/<version>/skills/<name>; the marketplace folder
# is optional here so a layout without it matches too.
PLUGIN_DIR = r"plugins/cache/(?:[^/\s]+/)?(?:dev-workbook|claudesidion)/"
LOAD_RE = re.compile(r"Base directory for this skill: \S*?" + PLUGIN_DIR + r"([^/\s]+)/skills/([^/\s]+)")
CACHE_RE = re.compile(PLUGIN_DIR + r"[^/\s]+/skills/")
PLUGINS = ("dev-workbook", "claudesidion")
VAULT_TOOLS = ("Read", "Edit", "Write", "Grep", "Glob", "Bash")
PATH_KEYS = ("file_path", "path", "notebook_path")
TOKEN_KEYS = (("input", "input_tokens"), ("cache_creation", "cache_creation_input_tokens"),
              ("cache_read", "cache_read_input_tokens"), ("output", "output_tokens"))
METRICS = (("skill_bytes", "skill B"), ("description_bytes", "desc B"),
           ("reference_bytes", "ref B"), ("vault_calls", "vault calls"),
           ("vault_result_bytes", "vault result B"),
           ("hook_context_bytes_all_plugins", "hook B (all plugins)"),
           ("plugin_bytes", "plugin B"))


def nbytes(s: str) -> int:
    return len(s.encode("utf-8", errors="replace"))


def content_text(c) -> str:
    """Text of a message's content, for sizing only."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def result_bytes(c) -> int:
    if isinstance(c, str):
        return nbytes(c)
    if isinstance(c, list):
        return sum(nbytes(b["text"]) if isinstance(b, dict) and isinstance(b.get("text"), str)
                   else nbytes(json.dumps(b)) for b in c)
    return 0 if c is None else nbytes(json.dumps(c))


# --- vault matching ---------------------------------------------------------------------

class Vault:
    def __init__(self, vault: str):
        given = os.path.abspath(os.path.expanduser(vault))
        self.forms = sorted({given.rstrip("/"), os.path.realpath(given).rstrip("/")})
        home = os.path.expanduser("~")
        self.cmd_forms = set(self.forms)
        for f in self.forms:
            if f.startswith(home + "/"):
                self.cmd_forms.add("~" + f[len(home):])
        alt = "|".join(re.escape(f) for f in sorted(self.cmd_forms, key=len, reverse=True))
        self.cmd_re = re.compile(
            r"(?:%s)(?=/|$|[\s\"';|&)<>`])|\$DEVWB_VAULT(?![A-Za-z0-9_])|\$\{DEVWB_VAULT\b" % alt)

    def has_path(self, p: str) -> bool:
        if not isinstance(p, str) or not p:
            return False
        p = os.path.expanduser(p)
        if not os.path.isabs(p):
            return False
        p = os.path.normpath(p)
        cands = {p, os.path.realpath(p)}
        return any(c == f or c.startswith(f + "/") for c in cands for f in self.forms)

    def call_in_vault(self, name: str, inp: dict) -> bool:
        if name == "Bash":
            return bool(self.cmd_re.search(str(inp.get("command", ""))))
        return any(self.has_path(inp.get(k)) for k in PATH_KEYS)


def call_is_reference(name: str, inp: dict) -> bool:
    if name == "Read":
        return bool(CACHE_RE.search(str(inp.get("file_path", ""))))
    if name == "Bash":
        return bool(CACHE_RE.search(str(inp.get("command", ""))))
    return False


# --- reading ----------------------------------------------------------------------------

def session_files(dirs: list[Path]) -> list[tuple[str, list[Path]]]:
    """(session key, files) in a stable order: the main file, then its subagents."""
    groups: dict[str, list[Path]] = {}
    for d in dirs:
        for f in sorted(d.glob("*.jsonl")):
            groups.setdefault(f"{d}/{f.stem}", []).append(f)
        for sub in sorted(d.glob("*/subagents/*.jsonl")):
            groups.setdefault(f"{d}/{sub.parent.parent.name}", []).append(sub)
    return sorted(groups.items())


def new_session(key: str) -> dict:
    return {"session": key.rsplit("/", 1)[-1], "ts": None, "repo": "", "cwd": "", "version": None,
            "loads": {}, "listings": set(), "description_bytes": 0, "reinjected_bytes": 0,
            "hook_context_bytes_all_plugins": 0, "reference_reads": 0, "reference_bytes": 0,
            "vault_calls": 0, "vault_input_bytes": 0, "vault_result_bytes": 0,
            "tokens": {k: 0 for k, _ in TOKEN_KEYS}}


def is_plugin_skill(name: str, path: str = "") -> bool:
    return name.split(":", 1)[0] in PLUGINS or bool(CACHE_RE.search(path or ""))


def read_session(files: list[Path], key: str, vault: Vault, seen: dict, ids: dict, stats: dict) -> dict:
    s = new_session(key)
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith('{"type":"api-request') or not line.lstrip().startswith("{"):
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    stats["malformed"] += 1
                    continue
                if not isinstance(o, dict) or o.get("type") not in KEPT:
                    continue
                note_identity(s, o)
                handle(s, o, vault, seen, ids)
    return s


def note_identity(s: dict, o: dict) -> None:
    ts = o.get("timestamp")
    if isinstance(ts, str):
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
            if s["ts"] is None or t < s["ts"]:
                s["ts"] = t
        except ValueError:
            pass
    cwd = o.get("cwd")
    if isinstance(cwd, str) and cwd and not s["cwd"]:
        s["cwd"] = cwd
        s["repo"] = os.path.basename(cwd.rstrip("/"))


def once(seen: dict, kind: str, ident) -> bool:
    """True the first time `ident` is seen for this kind across the whole run."""
    if not isinstance(ident, str) or not ident:
        return True
    bucket = seen.setdefault(kind, set())
    if ident in bucket:
        return False
    bucket.add(ident)
    return True


def handle(s: dict, o: dict, vault: Vault, seen: dict, ids: dict) -> None:
    kind = o["type"]
    if kind == "attachment":
        attachment(s, o, seen)
        return
    m = o.get("message")
    if not isinstance(m, dict):
        return
    if kind == "assistant":
        u = m.get("usage")
        if isinstance(u, dict) and once(seen, "msg", m.get("id")):
            for k, src in TOKEN_KEYS:
                v = u.get(src)
                s["tokens"][k] += v if isinstance(v, int) else 0
    c = m.get("content")
    if kind == "user" and o.get("isMeta"):
        injected(s, o, content_text(c), seen)
    if not isinstance(c, list):
        return
    for b in c:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_use" and kind == "assistant":
            tool_call(s, b, vault, seen, ids)
        elif b.get("type") == "tool_result" and kind == "user":
            tool_result(b, seen, ids)


def attachment(s: dict, o: dict, seen: dict) -> None:
    a = o.get("attachment")
    if not isinstance(a, dict) or not once(seen, "att", o.get("uuid")):
        return
    t = a.get("type")
    if t == "skill_listing" and isinstance(a.get("content"), str):
        if a["content"] in s["listings"]:
            return
        s["listings"].add(a["content"])
        for ln in a["content"].splitlines():
            if re.match(r"- (?:dev-workbook|claudesidion):", ln):
                s["description_bytes"] += nbytes(ln) + 1
    elif t == "invoked_skills" and isinstance(a.get("skills"), list):
        for sk in a["skills"]:
            if isinstance(sk, dict) and is_plugin_skill(str(sk.get("name", "")), str(sk.get("path", ""))):
                s["reinjected_bytes"] += nbytes(sk.get("content") if isinstance(sk.get("content"), str) else "")
    elif t == "hook_additional_context" and a.get("hookName") == "SessionStart":
        items = a.get("content")
        if isinstance(items, list):
            s["hook_context_bytes_all_plugins"] += sum(nbytes(i) for i in items if isinstance(i, str))


def injected(s: dict, o: dict, text: str, seen: dict) -> None:
    mt = LOAD_RE.match(text.lstrip())
    if not mt or not once(seen, "meta", o.get("uuid")):
        return
    ver, name = mt.groups()
    load = s["loads"].setdefault(o.get("sourceToolUseID") or "meta:" + str(o.get("uuid")),
                                 {"name": name, "bytes": 0, "version": ver})
    load.update(name=name, bytes=nbytes(text), version=ver)


def tool_call(s: dict, b: dict, vault: Vault, seen: dict, ids: dict) -> None:
    tid, name = b.get("id"), b.get("name")
    inp = b.get("input") if isinstance(b.get("input"), dict) else {}
    if not once(seen, "call", tid):
        return
    if name == "Skill":
        sk = str(inp.get("skill", ""))
        if sk.split(":", 1)[0] in PLUGINS:
            s["loads"].setdefault(tid, {"name": sk.split(":", 1)[1] if ":" in sk else sk,
                                        "bytes": 0, "version": None})
        return
    if name not in VAULT_TOOLS:
        return
    kinds = []
    if call_is_reference(name, inp):
        kinds.append("ref")
        s["reference_reads"] += 1
    if vault.call_in_vault(name, inp):
        kinds.append("vault")
        s["vault_calls"] += 1
        s["vault_input_bytes"] += nbytes(json.dumps(inp))
    if kinds and isinstance(tid, str):
        ids[tid] = (s, kinds)


def tool_result(b: dict, seen: dict, ids: dict) -> None:
    tid = b.get("tool_use_id")
    if tid not in ids or not once(seen, "result", tid):
        return
    s, kinds = ids[tid]
    n = result_bytes(b.get("content"))
    if "ref" in kinds:
        s["reference_bytes"] += n
    if "vault" in kinds:
        s["vault_result_bytes"] += n


# --- summarising ------------------------------------------------------------------------

def finish(s: dict) -> dict:
    loads = list(s["loads"].values())
    versions = [l["version"] for l in loads if l["version"]]
    s["version"] = versions[0] if versions else "unknown"
    s["skill_loads"] = len(loads)
    s["skill_bytes"] = sum(l["bytes"] for l in loads)
    s["plugin_bytes"] = (s["skill_bytes"] + s["description_bytes"] + s["reinjected_bytes"]
                         + s["reference_bytes"])
    return s


def row_json(s: dict) -> dict:
    return {"session": s["session"], "date": s["ts"].date().isoformat() if s["ts"] else None,
            "repo": s["repo"], "version": s["version"], "skill_loads": s["skill_loads"],
            "skill_bytes": s["skill_bytes"], "description_bytes": s["description_bytes"],
            "reinjected_bytes": s["reinjected_bytes"],
            "hook_context_bytes_all_plugins": s["hook_context_bytes_all_plugins"],
            "reference_reads": s["reference_reads"], "reference_bytes": s["reference_bytes"],
            "vault_calls": s["vault_calls"], "vault_input_bytes": s["vault_input_bytes"],
            "vault_result_bytes": s["vault_result_bytes"], "plugin_bytes": s["plugin_bytes"],
            "tokens": dict(s["tokens"])}


def p90(vals: list[int]) -> int:
    v = sorted(vals)
    return v[math.ceil(0.9 * len(v)) - 1]


def vkey(v: str) -> tuple:
    nums = re.findall(r"\d+", v)
    return (1, ()) if v == "unknown" else (0, tuple(int(n) for n in nums))


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["version"], []).append(r)
    out = []
    for ver in sorted(groups, key=vkey):
        g = groups[ver]
        item: dict = {"version": ver, "n": len(g)}
        for k, _ in METRICS:
            vals = [r[k] for r in g]
            item[k] = {"median": int(statistics.median(vals)),
                       "p90": p90(vals) if len(g) >= 10 else None}
        item["est_tokens"] = item["plugin_bytes"]["median"] // 4
        out.append(item)
    return out


def cell(m: dict) -> str:
    return str(m["median"]) if m["p90"] is None else f"{m['median']} (p90 {m['p90']})"


def print_rows(rows: list[dict]) -> None:
    print("| Date | Repo | Version | Loads | Skill B | Desc B | Re-injected B | Hook B (all plugins) "
          "| Ref reads | Ref B | Vault calls | Vault in B | Vault result B | Tokens in/cc/cr/out |")
    print("|" + " --- |" * 14)
    for r in rows:
        t = r["tokens"]
        print(f"| {r['date']} | {r['repo']} | {r['version']} | {r['skill_loads']} | {r['skill_bytes']} "
              f"| {r['description_bytes']} | {r['reinjected_bytes']} "
              f"| {r['hook_context_bytes_all_plugins']} | {r['reference_reads']} | {r['reference_bytes']} "
              f"| {r['vault_calls']} | {r['vault_input_bytes']} | {r['vault_result_bytes']} "
              f"| {t['input']}/{t['cache_creation']}/{t['cache_read']}/{t['output']} |")


def print_summary(summary: list[dict]) -> None:
    print("Median per session; p90 shown only when n >= 10. Bytes are in context; "
          "est. tokens = plugin bytes / 4.")
    print("| Version | n | " + " | ".join(label for _, label in METRICS) + " | est. tokens |")
    print("|" + " --- |" * (len(METRICS) + 3))
    for s in summary:
        print(f"| {s['version']} | {s['n']} | " + " | ".join(cell(s[k]) for k, _ in METRICS)
              + f" | est. {s['est_tokens']} |")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dev-workbook tokens", description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", type=Path, help="only this repo and its worktrees (default: every repo)")
    ap.add_argument("--transcripts", type=Path, nargs="+", action="extend", default=[],
                    metavar="DIR", help="transcript folder(s) to read instead of deriving them")
    ap.add_argument("--vault", help="vault path (default: resolved as the hooks do)")
    ap.add_argument("--since", type=date.fromisoformat, help="only sessions that started on or after")
    ap.add_argument("--sessions", type=int, metavar="N", help="only the N most recent counted sessions")
    ap.add_argument("--by", choices=("session", "version"), default="session")
    ap.add_argument("--json", action="store_true", help="print one object per session as a JSON array")
    a = ap.parse_args(argv)

    if a.transcripts:
        dirs = a.transcripts
    elif a.repo:
        dirs = transcript_dirs(a.repo)
    else:
        dirs = sorted(d for d in PROJECTS.iterdir() if d.is_dir()) if PROJECTS.is_dir() else []
    if not dirs:
        print(f"no transcripts found under {PROJECTS}", file=sys.stderr)
        return 1

    vault = Vault(str(paths.resolve_vault(a.vault)))
    seen: dict = {}
    ids: dict = {}
    stats = {"malformed": 0}
    sessions, left_out = [], 0
    for key, files in session_files(dirs):
        s = read_session(files, key, vault, seen, ids, stats)
        if s["cwd"] and vault.has_path(s["cwd"]):
            left_out += 1
            continue
        if not s["loads"] and not s["vault_calls"]:
            continue
        sessions.append(finish(s))
    if a.since:
        sessions = [s for s in sessions if s["ts"] and s["ts"].date() >= a.since]
    sessions.sort(key=lambda s: (s["ts"] is None, s["ts"].timestamp() if s["ts"] else 0, s["session"]))
    if a.sessions is not None:
        sessions = sessions[-a.sessions:] if a.sessions > 0 else []
    rows = [row_json(s) for s in sessions]

    if a.json:
        print(json.dumps(summarize(rows) if a.by == "version" else rows, indent=1))
    else:
        if a.by == "session":
            print_rows(rows)
            print()
        print_summary(summarize(rows))
    print(f"{len(rows)} session(s) counted; {left_out} run from inside the vault left out"
          + (f"; {stats['malformed']} malformed line(s) skipped" if stats["malformed"] else ""),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

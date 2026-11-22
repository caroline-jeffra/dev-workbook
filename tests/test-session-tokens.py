#!/usr/bin/env python3
"""Tests for scripts/session_tokens.py — the token-cost measurement.

    python3 tests/test-session-tokens.py
"""

from __future__ import annotations

import atexit
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import session_tokens as st  # noqa: E402

PASS = 0
FAIL: list[str] = []
SECRET = "SECRET-PLANTED-7f3a"


def check(cond: bool, name: str, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print(f"  \033[32mok\033[0m   {name}")
    else:
        FAIL.append(name)
        print(f"  \033[31mFAIL\033[0m {name}")
        if detail:
            print(f"       {detail}")


TMP = Path(tempfile.mkdtemp(prefix="devwb-tokens-")).resolve()
atexit.register(shutil.rmtree, TMP, ignore_errors=True)  # cleaned up even if a check raises
VAULT = TMP / "Vault"
VAULT.mkdir()
LINK = TMP / "vault-link"
LINK.symlink_to(VAULT)
CACHE = "/u/.claude/plugins/cache/dev-workbook/dev-workbook/3.4.0/skills"
CACHE_OLD = "/u/.claude/plugins/cache/claudesidion/3.0.2/skills"
REPO_SKILLS = "/u/code/dev-workbook/skills"

_n = [0]


def uid() -> str:
    _n[0] += 1
    return f"u{_n[0]}"


def base(kind: str, day: str = "2026-03-02", cwd: str = "/u/code/alpha", **kw) -> dict:
    return {"type": kind, "uuid": uid(), "timestamp": f"{day}T10:00:00Z", "cwd": cwd, **kw}


def assistant(blocks: list[dict], mid: str | None = None, usage: dict | None = None, **kw) -> dict:
    m: dict = {"role": "assistant", "content": blocks, "id": mid or uid()}
    if usage is not None:
        m["usage"] = usage
    return base("assistant", message=m, **kw)


def call(tid: str, name: str, **inp) -> dict:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def result(tid: str, text: str, **kw) -> dict:
    return base("user", message={"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text}]}, **kw)


def meta(text: str, source: str | None = None, **kw) -> dict:
    o = base("user", isMeta=True, message={"role": "user", "content": [{"type": "text", "text": text}]}, **kw)
    if source:
        o["sourceToolUseID"] = source
    return o


def skill_text(version: str, name: str, pad: int = 100, cache: str = "dev-workbook/dev-workbook") -> str:
    head = f"Base directory for this skill: /u/.claude/plugins/cache/{cache}/{version}/skills/{name}\n\n"
    return head + "x" * pad


def attach(kind: str, **fields) -> dict:
    return base("attachment", attachment={"type": kind, **fields})


def write(d: Path, name: str, records: list, raw: list[str] | None = None) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) if isinstance(r, dict) else r for r in records] + (raw or [])
    (d / f"{name}.jsonl").write_text("\n".join(lines) + "\n")
    return d / f"{name}.jsonl"


def run(args: list[str], d: Path, vault: Path = VAULT):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = st.main(["--transcripts", str(d), "--vault", str(vault), *args])
    return rc, out.getvalue(), err.getvalue()


def rows(d: Path, *args: str, vault: Path = VAULT) -> list[dict]:
    return json.loads(run(["--json", *args], d, vault)[1])


def fresh(name: str) -> Path:
    d = TMP / name
    shutil.rmtree(d, ignore_errors=True)
    return d


def only(d: Path, *args: str, **kw) -> dict:
    r = rows(d, *args, **kw)
    assert len(r) == 1, r
    return r[0]


def vault_read(tid: str, p: str | None = None) -> dict:
    return assistant([call(tid, "Read", file_path=p or f"{VAULT}/a.md")])


print("\nDuplicates")
d = fresh("dup")
c = assistant([call("t1", "Read", file_path=f"{VAULT}/a.md")])
write(d, "s1", [c, c, result("t1", "12345"), result("t1", "12345")])
r = only(d)
check(r["vault_calls"] == 1 and r["vault_result_bytes"] == 5, "a tool call duplicated in one file counts once", str(r))

d = fresh("resume")
recs = [vault_read("t1"), result("t1", "12345")]
write(d, "s1", recs)
write(d, "s2", recs + [vault_read("t2"), result("t2", "123")])
r = rows(d)
check(sum(x["vault_calls"] for x in r) == 2 and sum(x["vault_result_bytes"] for x in r) == 8,
      "records copied into a resumed session file count once", str(r))

d = fresh("sub")
write(d, "s1", [vault_read("t1"), result("t1", "12345")])
write(d / "s1" / "subagents", "agent-a", [vault_read("t1"), result("t1", "12345"),
                                          vault_read("t2"), result("t2", "123")])
r = rows(d)
check(len(r) == 1 and r[0]["vault_calls"] == 2 and r[0]["vault_result_bytes"] == 8,
      "subagent calls fold into the parent session and copies count once", str(r))

d = fresh("blob")
write(d, "s1", [vault_read("t1")],
      raw=[json.dumps({"type": "api-request-blob", "message": {"content": [
          call("t9", "Read", file_path=f"{VAULT}/b.md")]}})])
check(only(d)["vault_calls"] == 1, "an api-request-blob copy is ignored")

d = fresh("stream")
u = {"input_tokens": 3, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 7}
write(d, "s1", [assistant([call("t1", "Read", file_path=f"{VAULT}/a.md")], mid="m1", usage=u),
                assistant([{"type": "text", "text": "hi"}], mid="m1", usage=u),
                assistant([{"type": "text", "text": "ho"}], mid="m1", usage=u)])
check(only(d)["tokens"] == {"input": 3, "cache_creation": 100, "cache_read": 1000, "output": 7},
      "a streamed three-block turn counts its usage once")

print("\nSkill loads and re-injection")
d = fresh("loads")
text = skill_text("3.4.0", "manage-project-workspaces", pad=500)
slash = skill_text("3.4.0", "capture-notes", pad=200)
write(d, "s1", [assistant([call("sk1", "Skill", skill="dev-workbook:manage-project-workspaces")]),
                meta(text, source="sk1"), meta(slash)])
r = only(d)
check(r["skill_loads"] == 2 and r["skill_bytes"] == len(text) + len(slash) and r["version"] == "3.4.0",
      "a tool-call load and a slash-command load are counted, with bytes and version", str(r))

d = fresh("loads-old")
write(d, "s1", [meta(skill_text("3.0.2", "condense-vault", cache="claudesidion"))])
check(only(d)["version"] == "3.0.2", "the version comes from a cache path without a marketplace folder")

d = fresh("reinject")
write(d, "s1", [meta(skill_text("3.4.0", "capture-notes")),
                attach("invoked_skills", skills=[
                    {"name": "dev-workbook:capture-notes", "path": f"{CACHE}/capture-notes", "content": "a" * 300},
                    {"name": "other:thing", "path": "/u/other/skills/thing", "content": "b" * 999}])])
check(only(d)["reinjected_bytes"] == 300, "re-injection counts only dev-workbook skills")

d = fresh("desc")
listing = (f"- dev-workbook:capture-notes: {'d' * 50}\n- dev-workbook:condense-vault: {'e' * 20}\n"
           f"- other:thing: {SECRET}\n")
a1 = attach("skill_listing", content=listing)
want = len(f"- dev-workbook:capture-notes: {'d' * 50}") + 1 + len(f"- dev-workbook:condense-vault: {'e' * 20}") + 1
write(d, "s1", [a1, attach("skill_listing", content=listing), vault_read("t1")])
check(only(d)["description_bytes"] == want, "description bytes come from dev-workbook lines of skill_listing, once")

d = fresh("hook")
write(d, "s1", [attach("hook_additional_context", hookName="SessionStart", content=["a" * 40, "b" * 2]),
                vault_read("t1")])
r = only(d)
check(r["hook_context_bytes_all_plugins"] == 42 and "Hook B (all plugins)" in run([], d)[1],
      "hook context is the SessionStart total, named for all plugins")

print("\nReference reads")
d = fresh("ref")
write(d, "s1", [meta(skill_text("3.4.0", "x")),
                assistant([call("r1", "Read", file_path=f"{CACHE}/x/reference/a.md")]),
                result("r1", "abc"),
                assistant([call("r2", "Bash", command=f"sed -n 1,5p {CACHE_OLD}/x/reference/b.md")]),
                result("r2", "defg"),
                assistant([call("r3", "Read", file_path=f"{REPO_SKILLS}/x/reference/a.md")]),
                result("r3", "zzzzzzzz")])
r = only(d)
check(r["reference_reads"] == 2 and r["reference_bytes"] == 7, "cache reads and sed count; the plugin repo's skills do not", str(r))

print("\nVault calls")
d = fresh("vault")
write(d, "s1", [
    assistant([call("v1", "Read", file_path=f"{VAULT}/a.md")]), result("v1", "1"),
    assistant([call("v2", "Edit", file_path=f"{VAULT}/a.md", old_string="x", new_string="y")]), result("v2", "22"),
    assistant([call("v3", "Bash", command=f"cat {VAULT}/a.md | head")]), result("v3", "333"),
    assistant([call("v4", "Bash", command="ls /tmp")]), result("v4", "4444"),
    assistant([call("v5", "Read", file_path=f"{VAULT}2/a.md")]), result("v5", "55555"),
    assistant([call("v6", "Bash", command=f"cat {VAULT}2/a.md")]), result("v6", "666666"),
    assistant([call("v7", "Bash", command='ls "$DEVWB_VAULT"/notes')]), result("v7", "7777777"),
    assistant([call("v8", "Grep", pattern="x", path=str(VAULT))]), result("v8", "8"),
])
r = only(d)
check(r["vault_calls"] == 5 and r["vault_result_bytes"] == 1 + 2 + 3 + 7 + 1,
      "Read, Edit, Bash, $DEVWB_VAULT and Grep calls count; a non-vault Bash and Vault2 do not", str(r))

d = fresh("link")
write(d, "s1", [assistant([call("v1", "Read", file_path=f"{VAULT}/a.md")]), result("v1", "1"),
                assistant([call("v2", "Read", file_path=f"{LINK}/b.md")]), result("v2", "1")])
check(only(d, vault=LINK)["vault_calls"] == 2 and only(d, vault=VAULT)["vault_calls"] == 2,
      "a symlinked vault path counts, whichever form is given")

d = fresh("tilde")
home = TMP / "home"
tv = home / "notes-vault"
tv.mkdir(parents=True)
old_home = os.environ.get("HOME")
os.environ["HOME"] = str(home)  # a private home, so the test never touches the real one
try:
    write(d, "s1", [assistant([call("v1", "Read", file_path="~/notes-vault/a.md")]),
                    assistant([call("v2", "Bash", command="cat ~/notes-vault/a.md")])])
    check(only(d, vault=tv)["vault_calls"] == 2, "a ~ path counts")
finally:
    if old_home is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = old_home

d = fresh("boundary")
spaced = TMP / "My Vault"
spaced.mkdir()
write(d, "s1", [
    assistant([call("b1", "Bash", command=f"cat /backup{VAULT}/a.md")]),
    assistant([call("b2", "Glob", pattern=f"{VAULT}/**/*.md")]),
    assistant([call("b3", "Read", file_path=f"{VAULT}/a\x00.md")]),
])
check(only(d)["vault_calls"] == 1, "a Glob with an absolute pattern counts; a path ending in the vault's path and a NUL path do not")
write(fresh("spaced"), "s1", [assistant([call("e1", "Bash", command=f"cat {str(spaced).replace(' ', chr(92) + ' ')}/a.md")])])
check(only(TMP / "spaced", vault=spaced)["vault_calls"] == 1, "a backslash-escaped space in the vault path counts")

print("\nResumed sessions and subagent listings")
d = fresh("resume-order")
orig = [meta(skill_text("3.4.0", "capture-notes")) | {"timestamp": "2026-03-01T09:00:00Z"},
        vault_read("t1") | {"timestamp": "2026-03-01T09:01:00Z"}]
write(d, "z-original", orig)
write(d, "a-resume", orig + [vault_read("t2") | {"timestamp": "2026-03-03T09:00:00Z"}])
r = {x["session"]: x for x in rows(d)}
check(r["z-original"]["skill_loads"] == 1 and r["z-original"]["version"] == "3.4.0"
      and r["a-resume"]["skill_loads"] == 0 and r["a-resume"]["vault_calls"] == 1,
      "the earlier session keeps its records, whatever the file names", str(r))
check(r["a-resume"]["date"] == "2026-03-03", "a resumed session is dated by its own records, not the copies", str(r))

d = fresh("sub-listing")
dw = "- dev-workbook:capture-notes: " + "d" * 50
write(d, "s1", [attach("skill_listing", content=f"{dw}\n- other:a: x\n- other:b: y\n"), vault_read("t1")])
write(d / "s1" / "subagents", "agent-a", [attach("skill_listing", content=f"{dw}\n- other:a: x\n")])
check(only(d)["description_bytes"] == len(dw) + 1,
      "a subagent listing with the same dev-workbook lines adds no description bytes")

d = fresh("stream-max")
write(d, "s1", [assistant([call("t1", "Read", file_path=f"{VAULT}/a.md")], mid="m1", usage={"output_tokens": 2}),
                assistant([{"type": "text", "text": "x"}], mid="m1", usage={"output_tokens": 9})])
check(only(d)["tokens"]["output"] == 9, "a streamed turn keeps the largest usage seen, not the first")

print("\nWhich sessions count")
d = fresh("idle")
write(d, "s1", [assistant([call("v1", "Bash", command="ls /tmp")]), attach("skill_listing", content=listing)])
write(d, "s2", [vault_read("t1")])
r = rows(d)
check(len(r) == 1 and r[0]["session"] == "s2", "a session with only descriptions or non-vault calls is left out")

d = fresh("inside")
write(d, "s1", [vault_read("t1", f"{VAULT}/a.md") | {"cwd": f"{VAULT}/sub"}])
write(d, "s2", [vault_read("t2")])
rc, out, err = run(["--json"], d)
check(len(json.loads(out)) == 1 and "1 run from inside the vault" in err,
      "a session whose cwd is inside the vault is left out and counted on stderr", err)

d = fresh("filters")
write(d, "a", [vault_read("t1") | {"timestamp": "2026-01-05T10:00:00Z"}])
write(d, "b", [vault_read("t2") | {"timestamp": "2026-02-05T10:00:00Z"}])
write(d, "c", [vault_read("t3") | {"timestamp": "2026-03-05T10:00:00Z"}])
check([x["session"] for x in rows(d, "--since", "2026-02-01")] == ["b", "c"], "--since filters by start date")
check([x["session"] for x in rows(d, "--sessions", "2")] == ["b", "c"], "--sessions keeps the most recent")
write(d, "undated", [{k: v for k, v in vault_read("t4").items() if k != "timestamp"}])
check([x["session"] for x in rows(d, "--sessions", "2")] == ["b", "c"], "--sessions prefers dated sessions over undated ones")

print("\n--repo")
fake = TMP / "projects"
shutil.rmtree(fake, ignore_errors=True)
repo = TMP / "myrepo"
repo.mkdir(exist_ok=True)
from session_hours import encode  # noqa: E402

write(fake / encode(repo.resolve()), "s1", [vault_read("t1")])
write(fake / (encode(repo.resolve()) + "--claude-worktrees-w1"), "s2", [vault_read("t2")])
write(fake / "other-repo", "s3", [vault_read("t3")])
old = st.PROJECTS, st.transcript_dirs.__globals__["PROJECTS"]
st.PROJECTS = fake
st.transcript_dirs.__globals__["PROJECTS"] = fake
try:
    def run_repo(args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            st.main(["--vault", str(VAULT), "--json", *args])
        return json.loads(out.getvalue())
    check(sorted(x["session"] for x in run_repo(["--repo", str(repo)])) == ["s1", "s2"],
          "--repo reads the repo and its worktrees only")
    check(sorted(x["session"] for x in run_repo([])) == ["s1", "s2", "s3"], "the default reads every repo")
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        rc = st.main(["--vault", str(VAULT), "--repo", str(TMP / "no-such-repo")])
    check(rc == 1 and "no-such-repo" in err.getvalue(), "--repo with no transcripts names the repo", err.getvalue())
finally:
    st.PROJECTS = old[0]
    st.transcript_dirs.__globals__["PROJECTS"] = old[1]

print("\nSummary and output")
d = fresh("summary")
write(d, "a", [vault_read("t1")])
write(d, "b", [meta(skill_text("3.4.0", "x"))])
rc, out, err = run(["--by", "version"], d)
check("| unknown | 1 |" in out and "| 3.4.0 | 1 |" in out and "est." in out, "the version summary shows n and the unknown bucket", out)
check("alpha" not in out and "Date | Repo" not in out, "--by version prints no repo names or session rows")
rc, out, err = run([], d)
check("alpha" in out and "| 3.4.0 | 1 |" in out, "the default prints a row per session, then the summary")
check("(p90 " not in out, "no p90 below n = 10")
d = fresh("p90")
write(d, "s", [vault_read(f"t{i}") for i in range(1)])
for i in range(10):
    write(d, f"x{i}", [vault_read(f"p{i}")])
check("(p90 " in run(["--by", "version"], d)[1], "the p90 appears at n >= 10")
s10 = json.loads(run(["--json", "--by", "version"], d)[1])[0]
check(s10["n"] == 11 and s10["vault_calls"] == {"median": 1, "p90": 1}, "the p90 value is computed", str(s10))
d = fresh("p90-nine")
for i in range(9):
    write(d, f"x{i}", [vault_read(f"q{i}")])
check(json.loads(run(["--json", "--by", "version"], d)[1])[0]["vault_calls"]["p90"] is None, "no p90 at n = 9")
pv = st.p90(list(range(1, 11)))
check(pv == 9, "p90 of 1..10 is 9", str(pv))

print("\nRobustness and secrets")
d = fresh("secret")
secret_cmd = f"cat {VAULT}/{SECRET}.md {SECRET}"
write(d, "s1", [
    base("user", message={"role": "user", "content": f"please do {SECRET}"}),
    assistant([call("v1", "Bash", command=secret_cmd)]),
    result("v1", f"out {SECRET}"),
    assistant([call("v2", "Read", file_path=f"{VAULT}/{SECRET}.md")]),
    result("v2", SECRET),
    meta(skill_text("3.4.0", "x") + SECRET, source=None),
    attach("skill_listing", content=f"- dev-workbook:x: {SECRET}\n"),
    attach("hook_additional_context", hookName="SessionStart", content=[SECRET]),
], raw=['{"type":"user","message":{"content":"' + SECRET, "not json " + SECRET])
leaks = []
for args in ([], ["--by", "version"], ["--json"], ["--json", "--by", "version"]):
    rc, out, err = run(args, d)
    check(rc == 0, f"a malformed line does not crash the run {args}")
    if SECRET in out or SECRET in err:
        leaks.append(args)
check(not leaks, "a planted secret appears in neither stdout nor stderr", str(leaks))
rc, out, err = run([], d)
check("malformed" in err, "malformed lines are counted on stderr without their text", err)
r = json.loads(run(["--json"], d)[1])
check(isinstance(r, list) and r[0]["vault_calls"] == 2, "--json output parses")

d = fresh("odd")
write(d, "s1", [
    base("user", isMeta=True, message={"role": "user", "content": [{"type": "text", "text": 5}]}),
    assistant([{"type": "tool_use", "id": {"x": 1}, "name": "Skill", "input": {"skill": "dev-workbook:x"}}]),
    base("user", message={"role": "user", "content": [{"type": "tool_result", "tool_use_id": ["x"], "content": "z"}]}),
    vault_read("t1") | {"timestamp": "99999-01-01T00:00:00Z"},
])
write(d, "s2", [vault_read("t2") | {"cwd": "/u/a|b"}])
(d / "broken.jsonl").mkdir()  # a "transcript" that cannot be opened
rc, out, err = run([], d)
check(rc == 0 and "unreadable" in err, "odd record shapes and an unreadable file do not crash the run", err)
check("a\\|b" in out, "a | in a repo name is escaped in the session table", out)
rc, out, err = run([], TMP / "no-such-dir")
check(rc == 2 and "not a directory" in err, "a missing --transcripts folder is an error, not empty data", err)

print("\nCommand wiring")
d = fresh("cli")
write(d, "s1", [vault_read("t1"), result("t1", "12")])
p = subprocess.run([str(ROOT / "bin" / "dev-workbook"), "tokens", "--transcripts", str(d),
                    "--vault", str(VAULT), "--json"], capture_output=True, text=True)
try:
    cli = json.loads(p.stdout)
except json.JSONDecodeError:
    cli = None
check(p.returncode == 0 and cli and cli[0]["vault_calls"] == 1, "dev-workbook tokens runs the measurement", p.stderr)
h = subprocess.run([str(ROOT / "bin" / "dev-workbook"), "tokens", "--help"], capture_output=True, text=True)
check(h.returncode == 0 and all(o in h.stdout for o in ("--since", "--sessions", "--repo", "--transcripts",
                                                        "--vault", "--by", "--json")),
      "dev-workbook tokens --help lists the options")

print(f"\n{PASS} passed, {len(FAIL)} failed")
for f in FAIL:
    print(f"  - {f}")
sys.exit(1 if FAIL else 0)

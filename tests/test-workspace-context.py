#!/usr/bin/env python3
"""Tests for scripts/workspace_context.py — `dev-workbook context`, the one-line fact sheet skills read.

Every case builds a temp vault and code root; HOME, XDG_CONFIG_HOME, CODE_ROOT, DEVWB_VAULT and
CLAUDE_JOB_DIR are controlled so the real machine never leaks in. Run directly:

    python3 tests/test-workspace-context.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "hooks"), str(ROOT / "scripts")]

import dev_workbook_paths as paths  # noqa: E402
import workspace_context as wc  # noqa: E402

PASS = 0
FAIL: list[str] = []


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


def section(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")


TMP = Path(tempfile.mkdtemp(prefix="dev-workbook-context."))
HOME = TMP / "home"
HOME.mkdir()
for var in ("DEVWB_VAULT", "OBSIDIAN_VAULT", "CODE_ROOT", "CLAUDE_JOB_DIR"):
    os.environ.pop(var, None)
os.environ["HOME"] = str(HOME)
os.environ["XDG_CONFIG_HOME"] = str(TMP / "xdg")
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}


def sh(*cmd: str, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, env=GIT_ENV, check=True, capture_output=True)


def parse(line: str) -> dict[str, str]:
    """Parse one output line the way a reader would: split on spaces, un-quote JSON values."""
    out = {}
    for tok in split_tokens(line):
        k, _, v = tok.partition("=")
        out[k] = json.loads(v) if v.startswith('"') else v
    return out


def split_tokens(line: str) -> list[str]:
    toks, cur, quoted, esc = [], "", False, False
    for c in line:
        if quoted:
            cur += c
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
            cur += c
        elif c == " ":
            toks.append(cur)
            cur = ""
        else:
            cur += c
    toks.append(cur)
    return toks


def run(vault: Path | str | None, repo: Path | str | None, code_root: Path | None = None) -> dict[str, str]:
    argv = []
    if vault is not None:
        argv += ["--vault", str(vault)]
    if repo is not None:
        argv += ["--repo", str(repo)]
    if code_root is not None:
        os.environ["CODE_ROOT"] = str(code_root)
    try:
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "dev-workbook"), "context", *argv],
                           capture_output=True, text=True, env=os.environ)
    finally:
        os.environ.pop("CODE_ROOT", None)
    assert r.returncode == 0, r.stderr
    assert r.stdout.count("\n") == 1, r.stdout
    out = parse(r.stdout.rstrip("\n"))
    assert list(out) == list(wc.KEYS), list(out)
    return out


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    sh("git", "init", "-q", cwd=path)
    sh("git", "commit", "-q", "--allow-empty", "-m", "init", cwd=path)
    return path


INDEX_HEAD = "---\ncreated: 2026-07-10\n---\n\n# Project Workspaces\n\nIntro prose.\n\n| Repo path | Workspace |\n|---|---|\n"


def make_vault(name: str, rows: str, tail: str = "", index: str = "Projects/WorkspaceIndex.md",
               structured: tuple[str, ...] = ()) -> Path:
    v = TMP / name
    (v / "Projects").mkdir(parents=True)
    (v / "Projects" / ".dev-workbook-version").write_text("3.5.0\n")
    (v / index).write_text(INDEX_HEAD + rows + tail)
    for ws in structured:
        (v / "Projects" / ws).mkdir(parents=True, exist_ok=True)
        (v / "Projects" / ws / ".vault-config.json").write_text("{}")
    return v


CODE = TMP / "code"
CODE.mkdir()
alpha = git_repo(CODE / "alpha")
beta = git_repo(CODE / "beta")
budgeter = git_repo(CODE / "budgeter")
home_budgeter = git_repo(CODE / "home-budgeter")
spaced = git_repo(CODE / "my repo")

# ---------------------------------------------------------------------------
section("Matching: path, basename, moved, ambiguous")
# ---------------------------------------------------------------------------

REAL_ROWS = (
    "| alpha | [[Alpha/Overview]] |\n"
    "| `beta` | [[Projects/Beta/Overview\\|Beta project]] |\n"
    "| _(infra — no repo)_ | [[HomeServer/Overview]] |\n"
    "| (career) | [[Growth/Overview]] |\n"
    "| budgeter | [[Budgeter/Overview]] |\n"
    "| home-budgeter | [[HomeBudgeter/Overview]] |\n"
    "| my repo | [[SpacedRepo/Overview]] |\n"
)
NOTES = ("\nNote: `Projects/Old/` is **no longer written to**.\n\n"
         "## Trial workspaces\n\n| Repo path | Workspace |\n|---|---|\n| trialonly | [[Trial/Overview]] |\n"
         "| alpha | [[AlphaTrial/Overview]] |\n")
v = make_vault("real", REAL_ROWS, NOTES, structured=("Alpha", "Budgeter"))

r = run(v, alpha, CODE)
check(r["match"] == "path" and r["workspace"] == "Projects/Alpha", "path match", str(r))
check(r["structured"] == "yes", "a workspace with .vault-config.json is structured")
check(r["index"] == "Projects/WorkspaceIndex.md" and r["index_notes"] == "yes", "index and its notes are reported")
check(r["trial"] == "Projects/AlphaTrial", "a repo also under Trial workspaces reports it, main stays authoritative")
check(r["repo"] == str(alpha.resolve()) and r["code_root"] == str(CODE), "repo and code_root")
check(r["code_root_from"] == "env", "code_root_from=env")

r = run(v, beta, CODE)
check(r["match"] == "path" and r["workspace"] == "Projects/Beta", "backticked path and aliased `\\|` link", str(r))
check(r["structured"] == "no", "a workspace without .vault-config.json is not structured")
check(run(v, spaced, CODE)["workspace"] == "Projects/SpacedRepo", "a path with a space matches")
check(run(v, budgeter, CODE)["workspace"] == "Projects/Budgeter", "budgeter matches Budgeter")
check(run(v, home_budgeter, CODE)["workspace"] == "Projects/HomeBudgeter", "home-budgeter does not collide with budgeter")
# the same pair where the path stage misses, so the basename comparison itself decides
bud_root = TMP / "budgeter-root"
(bud_root / "old" / "budgeter").mkdir(parents=True)
(bud_root / "old" / "home-budgeter").mkdir(parents=True)
v_bud = make_vault("budgeter-basename", "| old/budgeter | [[Budgeter/Overview]] |\n"
                   "| old/home-budgeter | [[HomeBudgeter/Overview]] |\n")
r = run(v_bud, budgeter, bud_root)
check(r["match"] == "basename" and r["workspace"] == "Projects/Budgeter",
      "basename stage: budgeter matches only Budgeter", str(r))
r = run(v_bud, home_budgeter, bud_root)
check(r["match"] == "basename" and r["workspace"] == "Projects/HomeBudgeter",
      "basename stage: home-budgeter matches only HomeBudgeter", str(r))

# renamed clone: same repo, different folder name, no row → unmatched
clone = git_repo(CODE / "alpha-renamed-clone")
r = run(v, clone, CODE)
check(r["match"] == "unmatched" and r["workspace"] == "-", "a renamed clone is unmatched", str(r))

# trial-only repo
tonly = git_repo(CODE / "trialonly")
r = run(v, tonly, CODE)
check(r["match"] == "unmatched" and r["trial"] == "Projects/Trial", "trial-only repo: unmatched with trial set", str(r))

# basename: recorded path missing elsewhere vs present elsewhere
other_root = TMP / "other-root"
other_root.mkdir()
v2 = make_vault("basename", "| somewhere/else/alpha | [[Alpha/Overview]] |\n| beta | [[Beta/Overview]] |\n")
(other_root / "somewhere" / "else").mkdir(parents=True)
(other_root / "somewhere" / "else" / "alpha").mkdir()
r = run(v2, alpha, other_root)
check(r["match"] == "basename" and r["workspace"] == "Projects/Alpha" and r["indexed"] == "-",
      "basename match when the recorded path exists but is another checkout", str(r))
v3 = make_vault("moved", "| old/place/Alpha | [[Alpha/Overview]] |\n| beta | [[Beta/Overview]] |\n")
r = run(v3, alpha, CODE)
check(r["match"] == "moved" and r["indexed"] == "old/place/Alpha" and r["workspace"] == "Projects/Alpha",
      "moved: recorded path missing on this machine", str(r))
v4 = make_vault("ambig", "| x/alpha | [[One/Overview]] |\n| y/alpha | [[Two/Overview]] |\n| beta | [[Beta/Overview]] |\n")
r = run(v4, alpha, CODE)
check(r["match"] == "ambiguous" and r["candidates"] == "Projects/One,Projects/Two" and r["workspace"] == "-",
      "ambiguous lists candidates", str(r))
v5 = make_vault("same-ws", "| x/alpha | [[One/Overview]] |\n| y/alpha | [[One/Overview]] |\n| beta | [[B/Overview]] |\n")
check(run(v5, alpha, CODE)["match"] != "ambiguous", "two rows naming one workspace are not ambiguous")
check(run(make_vault("accents", "| café | [[Cafe/Overview]] |\n| beta | [[Beta/Overview]] |\n"),
          git_repo(CODE / "café"), CODE)["match"] == "path",
      "NFC/NFD folder names compare equal")

# new / misconfigured / unmatched
v6 = make_vault("new", "| _(infra — no repo)_ | [[HomeServer/Overview]] |\n")
check(run(v6, alpha, CODE)["match"] == "new", "only placeholder rows: new")
v7 = make_vault("misconf", "| nowhere/a | [[A/Overview]] |\n| nowhere/b | [[B/Overview]] |\n")
check(run(v7, alpha, CODE)["match"] == "misconfigured", "no row path exists on this machine: misconfigured")
check(run(v, TMP, CODE)["match"] == "unmatched",
      "a non-repo directory against a populated index: unmatched")

# no-index / no-vault
empty = TMP / "empty"
empty.mkdir()
r = run(empty, alpha, CODE)
check(r["match"] == "no-index" and r["consent"] == "ok" and r["index"] == "-", "empty vault: no-index, consent=ok", str(r))
r = run(TMP / "does-not-exist", alpha, CODE)
check(r["match"] == "no-vault" and r["vault_ok"] == "no", "missing vault: no-vault")

# ---------------------------------------------------------------------------
section("Worktrees, symlinks and macOS temp paths (the temp dir itself is /var -> /private/var)")
# ---------------------------------------------------------------------------

wt = TMP / "alpha-wt"
sh("git", "worktree", "add", "-q", str(wt), "-b", "wt-branch", cwd=alpha)
r = run(v, wt, CODE)
check(r["match"] == "path" and r["workspace"] == "Projects/Alpha", "a linked worktree matches its main checkout", str(r))
check(r["repo"] == str(wt.resolve()), "repo reports the worktree itself")

link_root = TMP / "link-root"
link_root.symlink_to(CODE)
check(run(v, alpha, link_root)["match"] == "path", "a symlinked code root still matches")
check(run(v, link_root / "alpha", CODE)["match"] == "path", "a repo reached through a symlink still matches")
sub = alpha / "sub" / "dir"
sub.mkdir(parents=True)
check(run(v, sub, CODE)["repo"] == str(alpha.resolve()), "from a subdirectory the repo is the toplevel")
abs_v = make_vault("abs", f"| {alpha} | [[Alpha/Overview]] |\n| beta | [[B/Overview]] |\n")
check(run(abs_v, alpha, other_root)["match"] == "path", "an absolute row is matched literally")

# ---------------------------------------------------------------------------
section("Index shapes")
# ---------------------------------------------------------------------------

legacy = make_vault("legacy", "| alpha | [[Alpha/Overview]] |\n| beta | [[B/Overview]] |\n", index="Projects/_index.md")
r = run(legacy, alpha, CODE)
check(r["index"] == "Projects/_index.md" and r["match"] == "path", "legacy _index.md is read", str(r))
check(run(make_vault("nonotes", "| alpha | [[Alpha/Overview]] |\n"), alpha, CODE)["index_notes"] == "no",
      "no prose after the table: index_notes=no")
hostile = make_vault("hostile", '| alpha | [[A"b c=d/Overview]] |\n| beta | [[B/Overview]] |\n')
r = run(hostile, alpha, CODE)
check(r["workspace"] == "-" and r["match"] == "unmatched", "a workspace name with quotes or `=` is not a workspace", str(r))

# ---------------------------------------------------------------------------
section("Consent")
# ---------------------------------------------------------------------------

c = TMP / "consent-empty"
c.mkdir()
check(run(c, alpha, CODE)["consent"] == "ok", "empty vault: ok")
c = TMP / "consent-foreign"
c.mkdir()
(c / "Stray.md").write_text("x")
check(run(c, alpha, CODE)["consent"] == "ask", "a foreign note: ask")
c = TMP / "consent-trash"
(c / ".trash").mkdir(parents=True)
(c / ".trash" / "Old.md").write_text("x")
check(run(c, alpha, CODE)["consent"] == "ask", "a note in .trash counts: ask")
c = TMP / "consent-git"
(c / ".git").mkdir(parents=True)
(c / ".git" / "x.md").write_text("x")
check(run(c, alpha, CODE)["consent"] == "ok", "markdown under .git does not count")
c = TMP / "consent-owned"
(c / "Resources").mkdir(parents=True)
(c / "Resources" / "R.md").write_text("x")
check(run(c, alpha, CODE)["consent"] == "ok", "notes only in this plugin's folders: ok")
c = TMP / "consent-unmanaged"
(c / "HouseStyles" / "Acme").mkdir(parents=True)
(c / "HouseStyles" / "Acme" / "PullRequest.md").write_text("x")
check(run(c, alpha, CODE)["consent"] == "ask", "notes in a folder nothing lists: ask")
(c / ".dev-workbook.json").write_text('{"unmanaged": ["HouseStyles"]}')
check(run(c, alpha, CODE)["consent"] == "ok", "notes only in a folder listed as unmanaged: ok")
c = TMP / "consent-projects"
(c / "Projects" / "Mine").mkdir(parents=True)
check(run(c, alpha, CODE)["consent"] == "ask", "Projects/ without a version file: ask")
(c / "Projects" / ".claudesidion-version").write_text("2.0\n")
check(run(c, alpha, CODE)["consent"] == "ok", "Projects/ with the old version file: ok")
c = TMP / "consent-index"
(c / "Projects").mkdir(parents=True)
(c / "Stray.md").write_text("x")
(c / "TasksArchive.md").write_text("x")
check(run(c, alpha, CODE)["consent"] == "ok", "TasksArchive present: ok even with other notes")
check(run(v, alpha, CODE)["consent"] == "ok", "index present: ok")
for name, marker in (("consent-wsindex", "Projects/WorkspaceIndex.md"), ("consent-legacy", "Projects/_index.md"),
                     ("consent-tasks-archive", "Tasks Archive.md")):
    c = TMP / name
    (c / "Projects").mkdir(parents=True)
    (c / "Stray.md").write_text("x")
    (c / marker).write_text("x")
    check(run(c, alpha, CODE)["consent"] == "ok",
          f"{marker} present, no version file, a stray note: ok")

# ---------------------------------------------------------------------------
section("Sync and background")
# ---------------------------------------------------------------------------

check(run(empty, alpha, CODE)["sync"] == "none", "a vault that is not a git work tree: none")
g = TMP / "gitvault"
g.mkdir()
sh("git", "init", "-q", cwd=g)
check(run(g, alpha, CODE)["sync"] == "self", "git vault without a heartbeat: self")
beat = g / ".git" / "dev-workbook-hooks"
beat.write_text("now\n")
check(run(g, alpha, CODE)["sync"] == "hooks", "fresh heartbeat: hooks")
old = time.time() - 25 * 3600
os.utime(beat, (old, old))
check(run(g, alpha, CODE)["sync"] == "self", "a 25-hour-old heartbeat: self")
fresh = time.time() - 23 * 3600
os.utime(beat, (fresh, fresh))
check(run(g, alpha, CODE)["sync"] == "hooks", "a 23-hour-old heartbeat: hooks")

check(run(g, alpha, CODE)["background"] == "no", "background=no by default")
os.environ["CLAUDE_JOB_DIR"] = "/x"
check(run(g, alpha, CODE)["background"] == "yes", "CLAUDE_JOB_DIR set: background=yes")
os.environ["CLAUDE_JOB_DIR"] = ""
check(run(g, alpha, CODE)["background"] == "no", "CLAUDE_JOB_DIR empty: background=no")
os.environ.pop("CLAUDE_JOB_DIR")

# ---------------------------------------------------------------------------
section("Quoting and errors")
# ---------------------------------------------------------------------------

line = wc.render({**{k: "-" for k in wc.KEYS}, "vault": "/a b\n/c\"d=e"})
check(line.count("\n") == 0 and parse(line)["vault"] == "/a b\n/c\"d=e", "whitespace, newline, quote and = stay on one line")
check(wc.fmt("plain/path") == "plain/path" and wc.fmt("") == "-" and wc.fmt(None) == "-", "plain values are bare, empty is -")
check(wc.fmt("a b").startswith('"') and " " not in wc.fmt("a b"), "unicode line separators are escaped")

real_gather = wc.gather


def boom(out, vault, repo):
    out["vault"] = "/partial"
    raise RuntimeError("forced")


wc.gather = boom
import io  # noqa: E402
import contextlib  # noqa: E402
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = wc.main([])
wc.gather = real_gather
out = parse(buf.getvalue().rstrip("\n"))
check(rc == 0 and list(out) == list(wc.KEYS) and out["error"].startswith("RuntimeError") and out["match"] == "-"
      and out["vault"] == "/partial", "an exception still prints every key plus error=", str(out))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = wc.main(["--bogus"])
check(rc == 0 and parse(buf.getvalue().rstrip("\n"))["error"] != "-", "a bad argument is reported in error=, exit 0")
check(run(empty, alpha, CODE)["error"] == "-", "no error: error=-")
check(run(TMP / "nope", TMP / "nope2", CODE)["repo"] == str(TMP / "nope2"), "a non-git, missing --repo falls back to that directory")

# ---------------------------------------------------------------------------
section("Unreadable index rows ask instead of scaffolding")
# ---------------------------------------------------------------------------

v_home = make_vault("home-links", "| alpha | [[Alpha/Home]] |\n| beta | [[Beta/Home]] |\n")
r = run(v_home, alpha, CODE)
check(r["match"] == "unmatched", "rows with no …/Overview link: unmatched, not new", str(r))
v_md = make_vault("md-links", "| alpha | [[Alpha/Overview.md]] |\n")
r = run(v_md, alpha, CODE)
check(r["match"] == "path" and r["workspace"] == "Projects/Alpha", "a [[X/Overview.md]] link is read", str(r))
v_trial_first = TMP / "trial-first"
(v_trial_first / "Projects").mkdir(parents=True)
(v_trial_first / "Projects" / "WorkspaceIndex.md").write_text(
    "# Project Workspaces\n\n## Trial workspaces\n\n| Repo path | Workspace |\n|---|---|\n"
    "| alpha | [[Alpha/Overview]] |\n")
r = run(v_trial_first, beta, CODE)
check(r["match"] == "unmatched", "trial section above the only table: unmatched, not new", str(r))

# ---------------------------------------------------------------------------
section("A wrong code root is misconfigured, not moved")
# ---------------------------------------------------------------------------

wrong_root = TMP / "wrong-root"
wrong_root.mkdir()
v_two = make_vault("two-rows", "| alpha | [[Alpha/Overview]] |\n| beta | [[Beta/Overview]] |\n")
r = run(v_two, alpha, wrong_root)
check(r["match"] == "misconfigured" and r["indexed"] == "-", "every row missing + basename hit: misconfigured", str(r))
v_one = make_vault("one-row", "| alpha | [[Alpha/Overview]] |\n")
r = run(v_one, alpha, wrong_root)
check(r["match"] == "moved", "a lone missing row with a basename hit stays moved (skill confirms)", str(r))
gamma = git_repo(CODE / "gamma")
r = run(v_two, gamma, CODE)
check(r["match"] == "unmatched", "rows exist on this machine, no hit: unmatched", str(r))
r = run(v_two, gamma, wrong_root)
check(r["match"] == "misconfigured", "no row exists on this machine, no hit: misconfigured", str(r))

# ---------------------------------------------------------------------------
section("Unsafe workspace names are not workspaces")
# ---------------------------------------------------------------------------

v_evil = make_vault("evil", "| alpha | [[$(touch pwned)/Overview]] |\n| beta | [[../Escape/Overview]] |\n"
                    "| gamma | [[Gamma`id`/Overview]] |\n")
for repo, label in ((alpha, "$( )"), (beta, ".."), (gamma, "backtick")):
    r = run(v_evil, repo, CODE)
    check(r["match"] == "unmatched" and r["workspace"] == "-", f"{label} in a workspace name: unmatched", str(r))
check("$(" not in run(v_evil, alpha, CODE)["candidates"], "no shell syntax reaches the output")
v_ok_names = make_vault("ok-names", "| alpha | [[bert.report/Overview]] |\n| beta | [[My Notes_2-x/Overview]] |\n")
check(run(v_ok_names, alpha, CODE)["workspace"] == "Projects/bert.report", "dots in a name are fine")
check(run(v_ok_names, beta, CODE)["workspace"] == "Projects/My Notes_2-x", "spaces, underscores, dashes are fine")

# A run of `[` in a row cost quadratic time in the wikilink pattern, stalling every skill's
# context call. The real row after it must still match.
import time  # noqa: E402
v_brackets = make_vault("brackets", "| junk | " + "[" * 100_000 + " |\n| alpha | [[Projects/Alpha/Overview\\|Alpha]] |\n")
start = time.monotonic()
r = run(v_brackets, alpha, CODE)
check(time.monotonic() - start < 3, "a row of 100k `[` does not stall the context call")
check(r["workspace"] == "Projects/Alpha", "and the row after it still matches", str(r))

# ---------------------------------------------------------------------------
section("vault_from")
# ---------------------------------------------------------------------------

check(run(v, alpha, CODE)["vault_from"] == "arg", "--vault: vault_from=arg")
os.environ["DEVWB_VAULT"] = str(TMP / "missing-vault")
try:
    r = run(None, alpha, CODE)
finally:
    os.environ.pop("DEVWB_VAULT")
check(r["vault_from"] == "env" and r["vault_ok"] == "no", "DEVWB_VAULT at a missing folder: vault_from=env vault_ok=no", str(r))

# ---------------------------------------------------------------------------
section("code_root_source agrees with resolve_code_root")
# ---------------------------------------------------------------------------

def tier(expect: str, name: str) -> None:
    check(paths.code_root_source() == expect, f"{name}: {paths.code_root_source()}")


tier("default", "nothing set")
check(paths.resolve_code_root() == HOME / "code", "default resolves to ~/code")
(HOME / ".claude").mkdir()
(HOME / ".claude" / "code-root").write_text("/legacy\n")
tier("legacy", "~/.claude/code-root")
check(str(paths.resolve_code_root()) == "/legacy", "legacy tier value")
(TMP / "xdg" / "claudesidion").mkdir(parents=True)
(TMP / "xdg" / "claudesidion" / "code-root").write_text("/old-config\n")
tier("legacy-config", "claudesidion config")
check(str(paths.resolve_code_root()) == "/old-config", "legacy-config tier value")
(TMP / "xdg" / "dev-workbook").mkdir()
(TMP / "xdg" / "dev-workbook" / "code-root").write_text("/new-config\n")
tier("config", "dev-workbook config")
check(str(paths.resolve_code_root()) == "/new-config", "config tier value")
os.environ["CODE_ROOT"] = "/from-env"
tier("env", "CODE_ROOT")
check(str(paths.resolve_code_root()) == "/from-env", "env tier value")
os.environ.pop("CODE_ROOT")
check(paths.vault_source() == "default", "vault_source: nothing set")
(TMP / "xdg" / "dev-workbook" / "vault").write_text("/v\n")
check(paths.vault_source() == "config" and str(paths.resolve_vault()) == "/v", "vault_source: config")
os.environ["OBSIDIAN_VAULT"] = "/legacy-env"
check(paths.vault_source() == "env", "vault_source: OBSIDIAN_VAULT is env")
os.environ.pop("OBSIDIAN_VAULT")

# Values that could read as extra keys to a model are quoted; readable text is left readable.
check(wc.fmt("a\u202eb") == '"a\\u202eb"', "a bidi control is quoted and escaped", wc.fmt("a\u202eb"))
check(wc.fmt("x\uff1dy").startswith('"'), "a look-alike = is quoted")
check(wc.fmt("/Users/x/Caf\u00e9") == '"/Users/x/Caf\u00e9"', "an accent stays readable")
check(wc.SAFE_NAME.fullmatch("Evil\n") is None, "a workspace name with a trailing newline is refused")

print(f"\n{PASS} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)

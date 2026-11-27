#!/usr/bin/env python3
"""Regression tests for hooks/vault_maintain.py.

Cases marked [T1.x] correspond to Pre-Release Plan tier-1 items. Run directly:

    python3 tests/test-vault-maintain.py
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS))

import vault_maintain as vm  # noqa: E402


def run_maintain(vault: Path) -> None:
    """Invoke the hook's entry point the way the real hook does (argv-driven)."""
    argv = sys.argv
    sys.argv = ["vault_maintain.py", str(vault)]
    try:
        vm.main()
    finally:
        sys.argv = argv

PASS = 0
FAIL: list[str] = []


def ok(name: str) -> None:
    global PASS
    PASS += 1
    print(f"  \033[32mok\033[0m   {name}")


def bad(name: str, detail: str = "") -> None:
    FAIL.append(name)
    print(f"  \033[31mFAIL\033[0m {name}")
    if detail:
        print(f"       {detail}")


def check(cond: bool, name: str, detail: str = "") -> None:
    ok(name) if cond else bad(name, detail)


def section(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")


# ---------------------------------------------------------------------------
section("[T1.4] Frontmatter must round-trip or the note is left alone")
# ---------------------------------------------------------------------------

# Each of these is YAML the hand-rolled parser cannot represent. The rule is not
# "parse it correctly" — it is "notice you cannot, and do not rewrite the file".
LOSSY = {
    "nested mapping": "nested:\n  key: value\n  deep:\n    more: 1\n",
    "block scalar": "multiline: |\n  line one\n  line two\n",
    "folded scalar": "description: >\n  folded text here\n",
    "comment line": "# a comment worth keeping\nkey: val\n",
    "nested list of maps": "items:\n  - name: a\n    id: 1\n",
}

for label, raw in LOSSY.items():
    check(
        not vm.frontmatter_roundtrips(raw),
        f"[T1.4] {label}: detected as not round-tripping",
        f"parser claims it can represent {raw!r}",
    )

SAFE = {
    "inline list": "tags: [a, b]\ntype: note\n",
    "block list": "tags:\n  - a\n  - b\n",
    "plain scalars": "type: decision\nstatus: active\n",
    "quoted colon": 'title: "a: b"\ntype: note\n',
    "empty then block list": "topics:\n  - one\n",
}

for label, raw in SAFE.items():
    check(
        vm.frontmatter_roundtrips(raw),
        f"[T1.4] {label}: recognised as safe to rewrite",
        "guard is too strict; this shape is representable",
    )

# ---------------------------------------------------------------------------
section("[T1.4] End to end: a lossy note survives a maintenance run")
# ---------------------------------------------------------------------------

tmp = Path(tempfile.mkdtemp(prefix="dev-workbook-vm-tests."))
try:
    ws = tmp / "Projects" / "Demo"
    (ws / "Notes").mkdir(parents=True)
    (ws / ".vault-config.json").write_text(
        '{"project":"demo","folders":{"note":"Notes"},"topics":{},'
        '"root_notes":[],"index_types":[],"generated_types":["index"]}',
        encoding="utf-8",
    )

    lossy = ws / "Notes" / "has-nested.md"
    lossy_text = (
        "---\n"
        "type: note\n"
        "status: reference\n"
        "dataview:\n"
        "  table: true\n"
        "  columns:\n"
        "    - file\n"
        "---\n\n"
        "# Nested\n\nBody text.\n"
    )
    lossy.write_text(lossy_text, encoding="utf-8")

    plain = ws / "Notes" / "plain.md"
    plain.write_text(
        "---\ntype: note\nstatus: reference\n---\n\n# Plain\n\nBody.\n", encoding="utf-8"
    )

    run_maintain(tmp)

    check(
        lossy.read_text(encoding="utf-8") == lossy_text,
        "[T1.4] note with nested frontmatter is byte-identical after a run",
        "the maintenance pass rewrote a note it could not represent",
    )
    check(
        "dataview" in lossy.read_text(encoding="utf-8"),
        "[T1.4] nested key survived",
    )
    check(
        "tags:" in plain.read_text(encoding="utf-8"),
        "[T1.4] a representable note is still maintained normally",
        "the guard is suppressing legitimate work",
    )

    # ---------------------------------------------------------------------
    section("[T1.5] Writes must stay inside the workspace")
    # ---------------------------------------------------------------------

    outside = tmp / "outside.md"
    outside_text = "---\ntype: note\nstatus: reference\n---\n\n# Outside\n"
    outside.write_text(outside_text, encoding="utf-8")
    link = ws / "Notes" / "linked.md"
    try:
        link.symlink_to(outside)
        run_maintain(tmp)
        check(
            outside.read_text(encoding="utf-8") == outside_text,
            "[T1.5] file outside the vault reached via symlink is not rewritten",
            "the maintenance pass followed a symlink out of the workspace",
        )
    except OSError:
        ok("[T1.5] symlink test skipped (unsupported on this filesystem)")

    # ---------------------------------------------------------------------
    section("[T1.6] Generated indexes must not clobber hand-written files")
    # ---------------------------------------------------------------------

    hand = ws / "TopicIndex.md"
    hand_text = "# Topic Index\n\nMy own carefully curated links.\n"
    hand.write_text(hand_text, encoding="utf-8")
    run_maintain(tmp)
    check(
        hand.read_text(encoding="utf-8") == hand_text,
        "[T1.6] pre-existing TopicIndex.md without the generated marker is preserved",
        "the hook overwrote a file the user wrote by hand",
    )

    # The refusal must say WHICH workspace: index filenames repeat across workspaces, so a
    # bare filename in a multi-workspace run cannot be traced back to a directory.
    import io, contextlib
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        run_maintain(tmp)
    msg = err.getvalue()
    check(
        "Demo" in msg and "TopicIndex.md" in msg,
        "[T1.6] the refusal names the workspace, not just the file",
        f"stderr was: {msg!r}",
    )
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ---------------------------------------------------------------------------
section("[T2.1] Threads and Decisions indexes are generated")
# ---------------------------------------------------------------------------

tmp2 = Path(tempfile.mkdtemp(prefix="dev-workbook-vm-t21."))
try:
    ws = tmp2 / "Projects" / "Demo"
    for folder in ("Threads", "Decisions", "Notes"):
        (ws / folder).mkdir(parents=True)
    (ws / ".vault-config.json").write_text(
        '{"project":"demo","folders":{"thread":"Threads","decision":"Decisions",'
        '"convention":"Decisions","note":"Notes"},"topics":{},'
        '"root_notes":[],"index_types":[],"generated_types":["index"]}',
        encoding="utf-8",
    )

    (ws / "Threads" / "Flaky deploys.md").write_text(
        "---\ntype: thread\nstatus: open\n---\n\n# Flaky deploys\n\n"
        "- [ ] one\n- [x] two\n- [ ] three\n",
        encoding="utf-8",
    )
    (ws / "Threads" / "Old cleanup.md").write_text(
        "---\ntype: thread\nstatus: done\n---\n\n# Old cleanup\n\n- [x] all done\n",
        encoding="utf-8",
    )
    (ws / "Decisions" / "Use Postgres.md").write_text(
        "---\ntype: decision\nstatus: active\ntickets: [ACME-1234, ACME-5678]\n---\n\n# Use Postgres\n",
        encoding="utf-8",
    )
    (ws / "Decisions" / "Use MySQL.md").write_text(
        "---\ntype: decision\nstatus: superseded\n---\n\n# Use MySQL\n",
        encoding="utf-8",
    )
    (ws / "Decisions" / "Trunk based.md").write_text(
        "---\ntype: convention\nstatus: active\n---\n\n# Trunk based\n",
        encoding="utf-8",
    )

    run_maintain(tmp2)

    threads_idx = ws / "ThreadsIndex.md"
    dec_idx = ws / "DecisionsIndex.md"

    check(threads_idx.is_file(), "[T2.1] ThreadsIndex.md is created")
    check(dec_idx.is_file(), "[T2.1] DecisionsIndex.md is created")

    if threads_idx.is_file():
        t = threads_idx.read_text(encoding="utf-8")
        check(vm.GENERATED_MARKER in t, "[T2.1] Threads Index carries the generated marker")
        check("Flaky deploys" in t, "[T2.1] Threads Index lists an open thread")
        check("Old cleanup" in t, "[T2.1] Threads Index lists a done thread")
        check("2" in t, "[T2.1] Threads Index reports an open count",
              "expected the 2 unchecked boxes of 'Flaky deploys' to be counted")

    if dec_idx.is_file():
        d = dec_idx.read_text(encoding="utf-8")
        check(vm.GENERATED_MARKER in d, "[T2.1] Decisions Index carries the generated marker")
        check("Use Postgres" in d, "[T2.1] Decisions Index lists an active decision")
        check("Use MySQL" in d, "[T2.1] Decisions Index lists a superseded decision")
        check("Trunk based" in d, "[T2.1] Decisions Index lists conventions too")
        # Ticket references are the one piece of a decision's context that is not in its
        # title; dropping them loses the link back to the work that prompted it.
        check("ACME-1234" in d and "ACME-5678" in d,
              "[T2.1] Decisions Index carries ticket references",
              "tickets: frontmatter was not surfaced in the index")

    # The indexes are themselves generated: they must not be swept into their own listing,
    # nor have their frontmatter rewritten by the metadata pass on the next run.
    before = (threads_idx.read_text(encoding="utf-8") if threads_idx.is_file() else "")
    run_maintain(tmp2)
    after = (threads_idx.read_text(encoding="utf-8") if threads_idx.is_file() else "")
    check(before == after, "[T2.1] a second run is a no-op on Threads Index",
          "the two writers are fighting over this file")

    # T1.6 protection must extend to the new indexes.
    hand = ws / "DecisionsIndex.md"
    hand.write_text("# Decisions Index\n\nHand written.\n", encoding="utf-8")
    run_maintain(tmp2)
    check(
        hand.read_text(encoding="utf-8") == "# Decisions Index\n\nHand written.\n",
        "[T2.1] an un-marked DecisionsIndex.md is not clobbered",
    )
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

# ---------------------------------------------------------------------------
section("[T2.9] Workspace discovery is not pinned to one depth")
# ---------------------------------------------------------------------------

tmp3 = Path(tempfile.mkdtemp(prefix="dev-workbook-vm-t29."))
try:
    CFG = ('{"project":"%s","folders":{"note":"Notes"},"topics":{},'
           '"root_notes":[],"index_types":[],"generated_types":["index"]}')

    # One workspace at each plausible depth, including the documented depth 2.
    places = {
        "root":   tmp3,
        "d1":     tmp3 / "Solo",
        "d2":     tmp3 / "Projects" / "Demo",
        "d3":     tmp3 / "Projects" / "Clients" / "Deep",
    }
    for name, ws in places.items():
        (ws / "Notes").mkdir(parents=True, exist_ok=True)
        (ws / ".vault-config.json").write_text(CFG % name, encoding="utf-8")
        (ws / "Notes" / "a.md").write_text(
            "---\ntype: note\nstatus: reference\n---\n\n# A\n", encoding="utf-8"
        )

    found = set(vm.find_workspaces(tmp3))
    for name, ws in places.items():
        check(ws in found, f"[T2.9] workspace at {name} is discovered",
              f"find_workspaces missed {ws}")

    # A nested workspace must not be claimed by its parent: the outer one owns its own
    # notes only, or the inner workspace's notes get indexed twice under two projects.
    check(
        len(found) == len(places),
        "[T2.9] each config yields exactly one workspace",
        f"expected {len(places)}, got {len(found)}: {sorted(map(str, found))}",
    )

    # .git and other dot-directories must never be walked.
    (tmp3 / ".git" / "hooks").mkdir(parents=True)
    (tmp3 / ".git" / "hooks" / ".vault-config.json").write_text(CFG % "git", encoding="utf-8")
    (tmp3 / ".obsidian").mkdir(exist_ok=True)
    (tmp3 / ".obsidian" / ".vault-config.json").write_text(CFG % "obs", encoding="utf-8")
    found2 = set(vm.find_workspaces(tmp3))
    check(
        not any(".git" in p.parts or ".obsidian" in p.parts for p in found2),
        "[T2.9] dot-directories are not searched",
        f"walked into a dot-directory: {sorted(map(str, found2))}",
    )
finally:
    shutil.rmtree(tmp3, ignore_errors=True)

# ---------------------------------------------------------------------------
section("Folder skeleton is fixed by the contract, not by config")
# ---------------------------------------------------------------------------

# New workspaces omit "folders" entirely: the skeleton is fixed by the workspace
# contract. If the default went missing, a note in Log/ with no declared type: would
# stop being inferred as a log, and every doctype tag would silently disappear.
tmp4 = Path(tempfile.mkdtemp(prefix="dev-workbook-vm-tests."))
try:
    ws = tmp4 / "Projects" / "Demo"
    (ws / "Log").mkdir(parents=True)
    (ws / "Decisions").mkdir(parents=True)
    # No "folders" key at all — exactly what scaffolding now writes.
    (ws / ".vault-config.json").write_text(
        json.dumps({"project": "demo", "topics": {}}), encoding="utf-8"
    )
    cfg = vm.Config.load(ws / ".vault-config.json")

    check(cfg.folders != {}, "folders defaults when the key is absent",
          "config with no folders key produced an empty map")
    check(cfg.doctype_for_folder("Log") == "log",
          "Log/ still infers type log", f"got {cfg.doctype_for_folder('Log')!r}")
    check(cfg.doctype_for_folder("Decisions") == "decision",
          "Decisions/ still infers type decision",
          f"got {cfg.doctype_for_folder('Decisions')!r}")
    check(cfg.doctype_for_folder("Threads") == "thread",
          "Threads/ still infers type thread",
          f"got {cfg.doctype_for_folder('Threads')!r}")

    # An explicit folders map must still win, so pre-contract workspaces keep working.
    (ws / ".vault-config.json").write_text(
        json.dumps({"project": "demo", "topics": {}, "folders": {"log": "Journal"}}),
        encoding="utf-8",
    )
    cfg2 = vm.Config.load(ws / ".vault-config.json")
    check(cfg2.doctype_for_folder("Journal") == "log",
          "an explicit folders map still overrides the default",
          f"got {cfg2.doctype_for_folder('Journal')!r}")
finally:
    shutil.rmtree(tmp4, ignore_errors=True)

# ---------------------------------------------------------------------------
section("Playbooks: a fixed folder, tracked with the threads")
# ---------------------------------------------------------------------------

tmp5 = Path(tempfile.mkdtemp(prefix="dev-workbook-vm-tests."))
try:
    ws = tmp5 / "Projects" / "Demo"
    (ws / "Playbooks").mkdir(parents=True)
    (ws / ".vault-config.json").write_text(
        json.dumps({"project": "demo", "topics": {}, "folders": {"log": "Journal"}}),
        encoding="utf-8",
    )
    cfg = vm.Config.load(ws / ".vault-config.json")
    check(cfg.doctype_for_folder("Playbooks") == "playbook",
          "Playbooks/ infers type playbook even when a config overrides another folder",
          f"got {cfg.doctype_for_folder('Playbooks')!r}")

    (ws / "Playbooks" / "CutoverToNewHostPlaybook.md").write_text(
        "---\nstatus: active\n---\n\n# Cutover to new host playbook\n\n"
        "**Goal:** move.\n\n**Done when:** it serves.\n\n## Steps\n\n- [ ] **1. Copy**\n- [x] **2. Plan**\n",
        encoding="utf-8",
    )
    (ws / "Playbooks" / "OldSetupPlaybook.md").write_text(
        "---\nstatus: reference\n---\n\n# Old setup playbook\n\n- [ ] **1. Step**\n",
        encoding="utf-8",
    )
    run_maintain(tmp5)
    idx = (ws / "ThreadsIndex.md").read_text(encoding="utf-8")
    check("Cutover to new host playbook" in idx and "**1 open**" in idx,
          "an active playbook is listed in the Threads Index with its open count", idx)
    check("Old setup" not in idx,
          "a reference playbook is not listed as open work", idx)
    check("type: playbook" in (ws / "Playbooks" / "CutoverToNewHostPlaybook.md").read_text(),
          "playbook type is filled in from the folder")
finally:
    shutil.rmtree(tmp5, ignore_errors=True)

# ---------------------------------------------------------------------------
section("Lint: clean notes are silent, each violation is reported")
# ---------------------------------------------------------------------------


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def lint_vault(vault: Path) -> list[str]:
    names = vm.VaultNames.scan(vault)
    out: list[str] = []
    wss = vm.find_workspaces(vault)
    for w in wss:
        c = vm.Config.load(w / ".vault-config.json")
        out += vm.lint(w, c, vm.collect(w, c), names, vault)
    return out + vm.lint_vault_level(vault, wss)


def codes_for(findings: list[str], name: str) -> set[str]:
    return {
        f.split(": ", 1)[1].split(" — ", 1)[0]
        for f in findings
        if f.split(": ", 1)[0] == name or f.split(": ", 1)[0].endswith("/" + name)
    }


tmp6 = Path(tempfile.mkdtemp(prefix="dev-workbook-vm-tests."))
try:
    ws = tmp6 / "Projects" / "Demo"
    write(ws / ".vault-config.json", json.dumps({"project": "demo", "topics": {}}))

    # --- clean, one per type
    write(ws / "Overview.md",
          "---\ntype: overview\nstatus: active\n---\n\n# demo\n\n**Repo path:** `demo`\n\n"
          "**Current focus:** cutover\n\n## Next up\n\n- Copy data — [[CutoverTracking]]\n")
    write(ws / "ProgressLog.md",
          "---\ntype: log-index\nstatus: reference\n---\n\n# Progress log — demo\n\n- **[[2026-10-01]]** — did a thing\n")
    write(ws / "Log" / "2026-10-01.md",
          "---\ntype: log\ndate: 2026-10-01\n---\n\n# 2026-10-01\n\n- **Did:** a thing\n"
          "- **Decided:** [[UseNewHost]]\n- **Links:** [[CutoverTracking]], [[ACME-12]], [[OldWork]]\n")
    write(ws / "Decisions" / "UseNewHost.md",
          "---\ntype: decision\nstatus: active\ndecided: 2026-10-01\nsupersedes: UseOldHost\n---\n\n"
          "# Use new host\n\n**Decision:** new host.\n\n**Why:** cheaper. Links [[UseOldHost]] as its predecessor.\n")
    write(ws / "Decisions" / "UseOldHost.md",
          "---\ntype: decision\nstatus: superseded\nsuperseded_by: UseNewHost\n---\n\n# Use old host\n\n**Decision:** old host.\n")
    write(ws / "Threads" / "CutoverTracking.md",
          "---\ntype: thread\nstatus: open\n---\n\n# Cutover tracking\n\n**Goal:** done.\n\n## Open\n\n- [ ] copy\n\n## Done\n\n- [x] plan\n")
    write(ws / "Threads" / "OldWork.md",
          "---\ntype: thread\nstatus: done\nclosed: 2026-09-01\n---\n\n# Old work\n\n**Goal:** g.\n\n"
          "**Outcome:** shipped.\n\n**Moved to:** [[UseNewHost]]\n")
    write(ws / "Research" / "HostCostsAnalysis.md",
          "---\ntype: research\nstatus: reference\n---\n\n# Host costs — analysis\n\n## TL;DR\n\n- cheaper\n\n"
          "Came out of [[OldWork]].\n\n- **Source:** a\n- **Date:** b\n")
    write(ws / "Playbooks" / "CutoverToNewHost.md",
          "---\ntype: playbook\nstatus: active\n---\n\n# Cutover to new host\n\n**Goal:** g\n\n"
          "**Done when:** d\n\n## Steps\n\n- [ ] **1. Copy**\n")
    write(ws / "Tickets" / "12-NaturalSortApi.md",
          "---\ntype: ticket\nstatus: active\ntickets: [ACME-12]\n---\n\n# ACME-12 natural sort API\n\n**Goal:** g\n\n"
          "**Status:** in review\n\n**Next:** merge once CI is green\n")
    write(ws / "TimeTracking.md",
          "---\ntype: time-tracking\nstatus: active\n---\n\n# Time tracking — demo\n\n**Budget:** 6 hrs/week\n\n"
          "## Phases\n\n| Phase | Status | Estimate | Actual |\n| --- | --- | --- | --- |\n| **0 Skeleton** | done | 12 | 7.89 |\n")
    write(tmp6 / "Resources" / "LinkChecker.md", "# Link checker\n")

    # --- one violation each
    write(ws / "Home.md", "# Home\n")
    write(ws / "Topic Index.md", "---\ntype: index\n---\n\n# Topic Index\n\n_Generated — edits here are overwritten._\n")
    write(ws / "Log" / "2026-10-02.md",
          "---\ntype: log\ndate: 2026-10-02\n---\n\n# 2026-10-02\n\n### Morning\n\n- **Did:** one\n"
          "- **Next:** two\n\n### Evening\n\n- **Did:** three\n")
    write(ws / "Decisions" / "we-use-postgres.md",
          "---\ntype: decision\nstatus: active\n---\n\n# We use Postgres\n\nSee [[DecisionsIndex]] and [[Decisions Index]].\n")
    write(ws / "Decisions" / "UseAWSForHosting.md",
          "---\ntype: decision\nstatus: active\n---\n\n# Use AWS for hosting\n\n**Decision:** AWS.\n")
    write(ws / "Threads" / "StalePointers.md",
          "---\ntype: thread\nstatus: open\n---\n\n# Stale pointers\n\n- [ ] follow [[UseOldHost]]\n"
          "- [ ] after [[OldWork]]\n- [ ] read [[NoSuchNote]]\n")
    write(ws / "Threads" / "TooLong.md",
          "---\ntype: thread\nstatus: open\n---\n\n# Too long\n\n- [ ] x\n\n" + ("word " * 400) + "\n")
    write(ws / "Threads" / "AllTicked.md",
          "---\ntype: thread\nstatus: open\n---\n\n# All ticked\n\n- [x] a\n- [x] b\n")
    write(ws / "Threads" / "DoneButFull.md",
          "---\ntype: thread\nstatus: done\n---\n\n# Done but full\n\n- [x] a\n- [ ] b\n")
    write(ws / "Research" / "Untitled findings.md",
          "---\ntype: research\nstatus: reference\n---\n\n# Untitled findings\n\nThis sentence was\nwrapped at a column.\n")
    write(ws / "Research" / "HostingNotes.md",
          "---\ntype: research\nstatus: reference\n---\n\n# Hosting\n\n## TL;DR\n\n- x\n")
    write(ws / "Playbooks" / "Deploy20261002Playbook.md",
          "---\ntype: playbook\nstatus: active\n---\n\n# Deploy\n\n- [ ] go\n")
    write(ws / "Tickets" / "ACME-13 old style.md",
          "---\ntype: ticket\nstatus: active\n---\n\n# ACME-13\n")
    write(ws / "Tickets" / "ACME-14-KeyedName.md",
          "---\ntype: ticket\nstatus: active\ntickets: [ACME-14]\n---\n\n# ACME-14 keyed name\n")
    write(ws / "Research" / "DemoHostingMap.md",
          "---\ntype: research\nstatus: reference\n---\n\n# Demo hosting map\n\n## TL;DR\n\n- x\n")
    write(ws / "Notes" / "Demolition.md",
          "---\ntype: note\nstatus: reference\n---\n\n# Demolition\n\nA word that starts with the project name.\n")
    write(ws / "Playbooks" / "RollbackPlaybook.md",
          "---\ntype: playbook\nstatus: active\n---\n\n# Rollback\n\n**Goal:** g\n\n**Done when:** d\n\n## Steps\n\n- [ ] go\n")
    write(ws / "Decisions" / "UseRedisCache.md",
          "---\ntype: decision\nstatus: active\nsupersedes: use-memcached\n---\n\n# Use Redis cache\n\n**Decision:** Redis.\n")
    write(tmp6 / "Archived" / "old" / "UseNewHost.md", "# dup\n")
    write(tmp6 / "Archived" / "old" / "not pascal.md", "# archived names are not checked\n")
    write(tmp6 / "HouseStyles" / "Acme" / "ticket-story.md", "# unmanaged folders are not checked\n")
    write(tmp6 / "Unlisted" / "not pascal either.md", "# a folder nobody lists is checked\n")
    write(tmp6 / ".dev-workbook.json", json.dumps({"unmanaged": ["HouseStyles"]}))
    write(tmp6 / "Tasks Archive.md", "# Tasks archive\n")
    write(tmp6 / "Resources" / "Link checker.md", "# Link checker\n")
    write(tmp6 / "Projects" / "home-thing" / ".vault-config.json", json.dumps({"project": "ht", "topics": {}}))

    # Lint runs on a maintained vault in practice: frontmatter filled in, indexes generated.
    write(ws / "Notes" / "StackedKeys.md",
          "---\ntype: note\nstatus: reference\n---\n\n# Stacked keys\n\n"
          "**Owner:** ops\n**Host:** new\n")
    write(ws / "Notes" / "TableAlias.md",
          "---\ntype: note\nstatus: reference\n---\n\n# Table alias\n\n"
          "| Day | Link |\n| --- | --- |\n| 1 | [[UseOldHost\\|old host]] |\n| 2 | [[UseOldHost]] |\n\n"
          "Prose keeps its [[UseOldHost|alias]], and code keeps `| [[a\\|b]] |`.\n")
    run_maintain(tmp6)
    check((ws / "TopicIndex.md").exists(), "fixture has generated indexes to ignore")
    findings = lint_vault(tmp6)

    for clean in ("Overview.md", "ProgressLog.md", "2026-10-01.md", "UseOldHost.md",
                  "CutoverTracking.md", "OldWork.md", "HostCostsAnalysis.md",
                  "CutoverToNewHost.md", "12-NaturalSortApi.md", "TimeTracking.md",
                  "LinkChecker.md", "TopicIndex.md"):
        got = codes_for(findings, clean)
        check(not got, f"clean {clean}: no findings", f"got {sorted(got)}")

    expect = {
        "Home.md": {"root-stray"},
        "Topic Index.md": {"legacy-name"},
        "2026-10-02.md": {"log-next", "log-stacked"},
        "we-use-postgres.md": {"bad-name", "index-link"},
        "UseAWSForHosting.md": {"bad-name"},
        "StalePointers.md": {"stale-link", "broken-link"},
        "TooLong.md": {"over-budget"},
        "AllTicked.md": {"unclosed-thread"},
        "DoneButFull.md": {"unclosed-thread"},
        "Untitled findings.md": {"bad-name", "missing-section", "hard-wrap"},
        "HostingNotes.md": {"bad-name"},
        "Deploy20261002Playbook.md": {"bad-name", "missing-section"},
        "ACME-13 old style.md": {"bad-name"},
        "ACME-14-KeyedName.md": {"bad-name"},
        "DemoHostingMap.md": {"bad-name"},
        "RollbackPlaybook.md": {"bad-name"},
        "Tasks Archive.md": {"legacy-name"},
        "Link checker.md": {"bad-name"},
        "StackedKeys.md": {"stacked-keys"},
        "TableAlias.md": {"table-alias"},
    }
    for name, want in expect.items():
        got = codes_for(findings, name)
        check(want <= got, f"{name}: reports {sorted(want)}", f"got {sorted(got)}")
    lognext = [f for f in findings if "2026-10-02.md: log-next" in f]
    check(len(lognext) == 1 and "ticket note or the Overview" in lognext[0],
          "a log's Next line is reported and points at the ticket note or the Overview", "\n".join(lognext))
    check(not [f for f in findings if "12-NaturalSortApi.md" in f],
          "a ticket's **Next:** line raises no finding")
    alias = [f for f in findings if "TableAlias.md: table-alias" in f]
    check(len(alias) == 1 and "1 aliased" in alias[0],
          "table-alias counts only aliased links in table rows", "\n".join(alias))

    check(any(f.startswith("Projects/home-thing/: bad-name") for f in findings),
          "a non-PascalCase workspace folder is reported", "\n".join(findings))
    check(not any("Archived/old/not pascal" in f for f in findings),
          "Archived/ names are not checked")
    check(not any("HouseStyles/" in f for f in findings),
          "names in a folder listed as unmanaged are not checked", "\n".join(findings))
    check(any("Unlisted/not pascal either" in f for f in findings),
          "names in a top-level folder nobody lists are still checked", "\n".join(findings))
    names6 = vm.VaultNames.scan(tmp6)
    check("ticket-story" not in names6.stems and not any(p.startswith("HouseStyles/") for p in names6.paths),
          "notes in an unmanaged folder stay out of link resolution")
    gen = [f for f in findings if "Topic Index.md" in f]
    check(bool(gen) and "delete it" in gen[0],
          "a pre-2.0 generated index is marked for deletion, not renaming", str(gen))
    dup = [f for f in findings if f.startswith("Projects/Demo/Decisions/UseNewHost.md: dup-name")]
    check(bool(dup) and "Archived/old/UseNewHost.md" in dup[0],
          "dup-name says where the other copy is", str(dup))
    stale = [f for f in findings if "StalePointers.md: stale-link" in f]
    check(bool(stale) and "UseOldHost" in stale[0] and "OldWork" in stale[0],
          "stale-link names both the superseded decision and the done thread", str(stale))
    fm_ref = [f for f in findings if f.startswith("Projects/Demo/Decisions/UseRedisCache.md: broken-link")]
    check(bool(fm_ref) and "supersedes: use-memcached" in fm_ref[0],
          "a supersedes: value naming no note is reported", str(fm_ref))
    check(not codes_for(findings, "UseNewHost.md") - {"dup-name"},
          "a supersedes: value naming a real note is not reported")
    check(not any("[[ACME-12]]" in f for f in findings),
          "a bare ticket-ID link is a placeholder, not a broken link")
    check(not codes_for(findings, "Demolition.md"),
          "a name that merely starts with the project's letters is not a project prefix")
    keyed = [f for f in findings if "ACME-14-KeyedName.md: bad-name" in f]
    check(bool(keyed) and "project key" in keyed[0], "a keyed ticket name is told to drop the key", str(keyed))
    prefixed = [f for f in findings if "DemoHostingMap.md: bad-name" in f]
    check(bool(prefixed) and "project name" in prefixed[0], "a project-prefixed name is told to drop it", str(prefixed))
    tickets = (ws / "TicketsIndex.md").read_text()
    check("**[[12-NaturalSortApi|ACME-12]]**" in tickets,
          "a <number>-<Subject> ticket note owns its key from tickets:", tickets)

    # The CLI: lint writes nothing, and --count prints just the number.
    before = {p: p.read_bytes() for p in tmp6.rglob("*.md")}
    import io
    import contextlib
    buf = io.StringIO()
    argv = sys.argv
    sys.argv = ["vault_maintain.py", "--lint", "--count", str(tmp6)]
    try:
        with contextlib.redirect_stdout(buf):
            vm.main()
    finally:
        sys.argv = argv
    check(buf.getvalue().strip() == str(len(findings)),
          "--lint --count prints the number of findings", repr(buf.getvalue()))
    after = {p: p.read_bytes() for p in tmp6.rglob("*.md")}
    check(before == after, "--lint writes nothing")
finally:
    shutil.rmtree(tmp6, ignore_errors=True)

# ---------------------------------------------------------------------------
section("Links: generated and linted links name exactly one note")
# ---------------------------------------------------------------------------

tmp7 = Path(tempfile.mkdtemp(prefix="dev-workbook-vm-tests."))
try:
    for proj in ("Alpha", "Beta"):
        w = tmp7 / "Projects" / proj
        write(w / ".vault-config.json", json.dumps({
            "project": proj.lower(),
            "topics": {"cache": {"name": "Cache", "patterns": ["cache"]}},
        }))
        write(w / "Overview.md", f"---\ntype: overview\nstatus: active\n---\n\n# {proj}\n\n## Next up\n\n- x\n")
        # Both workspaces logged 2026-10-01; only Alpha logged 2026-10-02.
        write(w / "Log" / "2026-10-01.md",
              "---\ntype: log\ndate: 2026-10-01\n---\n\n# 2026-10-01\n\n- **Did:** cache cache cache\n")
    alpha = tmp7 / "Projects" / "Alpha"
    write(alpha / "Log" / "2026-10-02.md",
          "---\ntype: log\ndate: 2026-10-02\n---\n\n# 2026-10-02\n\n- **Did:** cache cache cache\n")
    write(alpha / "Threads" / "WarmTheCache.md",
          "---\ntype: thread\nstatus: open\n---\n\n# Warm the cache\n\n- [ ] cache cache cache\n")
    write(alpha / "ProgressLog.md",
          "---\ntype: log-index\nstatus: reference\n---\n\n# Progress log\n\n"
          "- **[[2026-10-02]]** — unique\n- **[[2026-10-01]]** — ambiguous\n"
          "- **[[Alpha/Log/2026-10-01|2026-10-01]]** — qualified\n- [[warmthecache]] by case\n")

    for proj in ("Alpha", "Beta"):
        write(tmp7 / "Projects" / proj / "Threads" / "CompletedItems.md",
              "---\ntype: thread\nstatus: open\n---\n\n# Completed items\n\n- [ ] x\n")
    write(alpha / "Notes" / "SharedNameLinks.md",
          "---\ntype: note\nstatus: reference\n---\n\n# Shared name links\n\n"
          "See [[CompletedItems]] and [[Alpha/Threads/CompletedItems]].\n")

    run_maintain(tmp7)
    topic = (alpha / "TopicIndex.md").read_text()
    check("[[Alpha/Log/2026-10-01|2026-10-01]]" in topic,
          "a log date another workspace shares is linked by its workspace path", topic)
    check("[[2026-10-02]]" in topic, "a unique log date stays bare", topic)
    check("[[WarmTheCache|Warm the cache]]" in topic or "[[WarmTheCache]]" in topic,
          "a unique note stays bare", topic)
    check("[C](#c)" in topic and "[[#" not in topic,
          "letter nav is a standard anchor link, not a heading wikilink", topic)
    threads = (alpha / "ThreadsIndex.md").read_text()
    check("[[WarmTheCache|Warm the cache]]" in threads, "thread index link is bare and titled", threads)

    findings = lint_vault(tmp7)
    amb = [f for f in findings if f.startswith("Projects/Alpha/ProgressLog.md: ambiguous-link")]
    check(len(amb) == 1 and "[[2026-10-01]]" in amb[0] and "2026-10-02" not in amb[0]
          and "Alpha/Log" not in amb[0],
          "ambiguous-link names only the bare shared date", "\n".join(findings))
    check(not any("broken-link" in f and "warmthecache" in f for f in findings),
          "links resolve case-insensitively, as every viewer does", "\n".join(findings))
    check(not any("ambiguous-link" in f for f in findings if "TopicIndex" in f or "Index.md" in f),
          "generated indexes are never ambiguous")
    check(not any("dup-name" in f and "CompletedItems" in f for f in findings),
          "two workspaces may share a note name", "\n".join(findings))
    shared = [f for f in findings if f.startswith("Projects/Alpha/Notes/SharedNameLinks.md: ambiguous-link")]
    check(len(shared) == 1 and "[[CompletedItems]]" in shared[0] and "Alpha/Threads" not in shared[0],
          "a bare link to a name two workspaces share is ambiguous; a qualified one is not", "\n".join(findings))

    names = vm.VaultNames.scan(tmp7)
    check(names.matches("2026-10-01") == 2 and names.matches("Alpha/Log/2026-10-01") == 1
          and names.matches("log/2026-10-02") == 1,
          "matches counts notes by path suffix, case-insensitively")
finally:
    shutil.rmtree(tmp7, ignore_errors=True)

# ---------------------------------------------------------------------------
section("Diagrams: Excalidraw drawings are named and linked, never rewritten")
# ---------------------------------------------------------------------------

DRAWING = (
    "---\n\nexcalidraw-plugin: parsed\ntags: [excalidraw]\n\n---\n"
    "==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠==\n\n\n"
    "# Excalidraw Data\n\n## Text Elements\nApi gateway ^a1b2c3d4\n\nQueue worker ^e5f6g7h8\n\n"
    "%%\n## Drawing\n```compressed-json\nN4KAkARALgngDgUwgLgAQQQDwMYEMA2AlgCYBOuA7hADTgQBuCpAzoQPYB2KqATLZMzYBXUtiRoIACyhQ4zZAHoFAc0JRJQgEYA6bGwC2CgF7N6hbEcK4OCtptbErHALRY8RMpWdx8Q1TdIEfARcZgRmBShcZQUebQBGAA4ePzKFNgA5JGMjEUwALSpxIuo\n```\n%%\n"
)

tmp9 = Path(tempfile.mkdtemp(prefix="dev-workbook-vm-tests."))
try:
    ws = tmp9 / "Projects" / "Demo"
    write(ws / ".vault-config.json", json.dumps({
        "project": "demo", "topics": {"queue": {"name": "Queue", "patterns": ["queue"]}},
    }))
    write(ws / "Overview.md", "---\ntype: overview\nstatus: active\n---\n\n# Demo\n\n## Next up\n\n- x\n")
    write(ws / "Diagrams" / "SystemContext.excalidraw.md", DRAWING)
    write(ws / "Diagrams" / "QueueFlow.md",
          "---\nstatus: reference\n---\n\n# Queue flow\n\nHow a job moves through the queue queue queue.\n\n"
          "```mermaid\nflowchart LR\n  api --> queue --> worker\n```\n")
    write(ws / "Research" / "SystemContextMap.md",
          "---\ntype: research\nstatus: reference\n---\n\n# System context map\n\n## TL;DR\n\n"
          "- Three parts.\n\n![[SystemContext.excalidraw]]\n\nAlso [[SystemContext.excalidraw|the drawing]], "
          "[[QueueFlow]] and ![[MissingSketch.excalidraw]].\n")
    write(ws / "Notes" / "Misfiled.excalidraw.md", DRAWING)
    write(ws / "Diagrams" / "Drawing 2026-11-15 10.22.33.excalidraw.md", DRAWING)

    run_maintain(tmp9)
    check((ws / "Diagrams" / "SystemContext.excalidraw.md").read_text() == DRAWING,
          "the maintainer never rewrites a drawing")
    check("type: diagram" in (ws / "Diagrams" / "QueueFlow.md").read_text(),
          "a note in Diagrams/ is typed diagram")
    topic = (ws / "TopicIndex.md").read_text()
    check("**Diagram** (1)" in topic and "SystemContext.excalidraw" not in topic,
          "a Mermaid diagram note is indexed; a drawing carries no topics", topic)

    findings = lint_vault(tmp9)
    check(not codes_for(findings, "SystemContext.excalidraw.md"),
          "a well-placed drawing raises no findings", "\n".join(findings))
    check(not codes_for(findings, "QueueFlow.md"), "a Mermaid diagram note is clean", "\n".join(findings))
    broken = [f for f in findings if f.startswith("Projects/Demo/Research/SystemContextMap.md: broken-link")]
    check(len(broken) == 1 and "MissingSketch.excalidraw" in broken[0] and "SystemContext.excalidraw]]" not in broken[0],
          "an embedded drawing resolves; an embed of a missing one is broken", "\n".join(findings))
    check(any("Misfiled.excalidraw.md: bad-name" in f and "Diagrams/" in f for f in findings),
          "a drawing outside Diagrams/ is reported", "\n".join(findings))
    check("bad-name" in codes_for(findings, "Drawing 2026-11-15 10.22.33.excalidraw.md"),
          "the plugin's default drawing name is reported", "\n".join(findings))
    check(not any("hard-wrap" in f or "stacked-keys" in f for f in findings if ".excalidraw" in f),
          "a drawing's body is not linted as prose", "\n".join(findings))
finally:
    shutil.rmtree(tmp9, ignore_errors=True)

# ---------------------------------------------------------------------------
section("Stale-session guard: an older maintainer leaves a newer vault alone")
# ---------------------------------------------------------------------------

tmp8 = Path(tempfile.mkdtemp(prefix="dev-workbook-vm-tests."))
real_own = vm.own_version
try:
    ws = tmp8 / "Projects" / "Demo"
    write(ws / ".vault-config.json", json.dumps({"project": "demo", "topics": {}}))
    write(ws / "Overview.md", "---\ntype: overview\nstatus: active\n---\n\n# demo\n")
    record = tmp8 / "Projects" / ".dev-workbook-version"

    check(vm.parse_version(real_own()) is not None, "own_version reads plugin.json")

    vm.own_version = lambda: "2.4.0"
    run_maintain(tmp8)
    check(record.read_text() == "2.4.0\n", "a maintenance run records its version")
    check((ws / "TopicIndex.md").exists(), "and maintains as normal")

    (ws / "TopicIndex.md").unlink()
    vm.own_version = lambda: "2.3.9"
    run_maintain(tmp8)
    check(not (ws / "TopicIndex.md").exists(), "an older maintainer writes nothing")
    check(record.read_text() == "2.4.0\n", "and never lowers the recorded version")

    vm.own_version = lambda: "2.10.0"
    argv, sys.argv = sys.argv, ["vault_maintain.py", "--claim", str(tmp8)]
    try:
        vm.main()
    finally:
        sys.argv = argv
    check(record.read_text() == "2.10.0\n", "--claim raises the record (numeric, not string, order)")
    check(not (ws / "TopicIndex.md").exists(), "--claim maintains nothing")

    record.write_text("garbage\n")
    vm.own_version = lambda: "2.3.9"
    run_maintain(tmp8)
    check((ws / "TopicIndex.md").exists(), "an unreadable record disables the guard, not the maintainer")
    check(record.read_text() == "2.3.9\n", "and is replaced with a valid one")

    bare = tmp8 / "bare"
    bare.mkdir()
    vm.claim(bare, "9.9.9")
    check(not (bare / "Projects").exists(), "claim never creates Projects/")

    vm.own_version = lambda: None
    run_maintain(tmp8)
    check(record.read_text() == "2.3.9\n", "an unknown own version claims nothing")

    legacy = tmp8 / "Projects" / ".claudesidion-version"
    legacy.write_text("2.6.0\n")
    (ws / "TopicIndex.md").unlink()
    vm.own_version = lambda: "2.5.0"
    run_maintain(tmp8)
    check(not (ws / "TopicIndex.md").exists(), "a newer pre-3.0 record still trips the guard")

    vm.own_version = lambda: "3.0.0"
    run_maintain(tmp8)
    check(record.read_text() == "3.0.0\n", "the claim goes to the current file")
    check(legacy.read_text() == "2.6.0\n", "and the pre-3.0 file is left alone")
finally:
    vm.own_version = real_own
    shutil.rmtree(tmp8, ignore_errors=True)

# ---------------------------------------------------------------------------
section("Symlinks from the vault's remote never redirect a write")
# ---------------------------------------------------------------------------

tmp9 = Path(tempfile.mkdtemp())
real_own = vm.own_version
try:
    outside = tmp9 / "outside"
    outside.mkdir()
    victim = outside / "victim.txt"
    victim.write_text("precious\n")
    vault = tmp9 / "vault"
    ws = vault / "Projects" / "W"
    ws.mkdir(parents=True)
    (vault / "Projects" / ".dev-workbook-version").symlink_to(victim)
    vm.own_version = lambda: "9.9.9"
    run_maintain(vault)
    check(victim.read_text() == "precious\n", "the version claim does not write through a symlink")

    (vault / "Projects" / ".dev-workbook-version").unlink()
    write(ws / ".vault-config.json", json.dumps(
        {"project": "w", "topics": {"t": {"name": "T", "gloss": "x\nINJECTED LINE", "patterns": ["zzz"]}}}))
    write(ws / "Notes" / "N.md", "---\ntype: note\ntopics: [t]\n---\n\n# N\n")
    for name in ("TopicIndex.md", "ThreadsIndex.md"):
        (ws / name).symlink_to(outside / f"new-{name}")
    run_maintain(vault)
    check(not (outside / "new-TopicIndex.md").exists() and not (outside / "new-ThreadsIndex.md").exists(),
          "an index that is a dangling symlink is not written through")
    for name in ("TopicIndex.md", "ThreadsIndex.md"):
        (ws / name).unlink()
    run_maintain(vault)
    topic = (ws / "TopicIndex.md").read_text()
    check("\nINJECTED LINE" not in topic and "x INJECTED LINE" in topic,
          "a newline in a topic gloss stays on the gloss's line", topic)
    check(not list(ws.glob(".*.tmp")), "no temporary files are left behind")
finally:
    vm.own_version = real_own
    shutil.rmtree(tmp9, ignore_errors=True)

# ---------------------------------------------------------------------------
section("A note edited while the run is going is not overwritten")
# ---------------------------------------------------------------------------

tmp10 = Path(tempfile.mkdtemp())
try:
    ws = tmp10 / "Projects" / "W"
    write(ws / ".vault-config.json", json.dumps({"project": "w", "topics": {}}))
    note = ws / "Notes" / "Busy.md"
    write(note, "# Busy\n\nfirst line\n")
    cfg = vm.Config.load(ws / ".vault-config.json")
    notes = vm.collect(ws, cfg)
    note.write_text("# Busy\n\nfirst line\nsaved by the editor mid-run\n")
    vm.refresh_metadata(notes, cfg)
    check("saved by the editor mid-run" in note.read_text(), "the concurrent edit survives")
    vm.refresh_metadata(vm.collect(ws, cfg), cfg)
    text = note.read_text()
    check(text.startswith("---") and "saved by the editor mid-run" in text,
          "the next run adds the frontmatter around it", text)
finally:
    shutil.rmtree(tmp10, ignore_errors=True)

# ---------------------------------------------------------------------------
section("Empty values round-trip, so template notes stay maintainable")
# ---------------------------------------------------------------------------

# The decision and playbook templates write `tickets: []`. The emitter used to drop empty values,
# so no such note round-tripped and every one was skipped on every run.
tmp13 = Path(tempfile.mkdtemp())
try:
    ws = tmp13 / "Projects" / "W"
    write(ws / ".vault-config.json", json.dumps({"project": "w", "topics": {}}))
    note = ws / "Decisions" / "UseQueues.md"
    write(note, "---\ntype: decision\nstatus: active\ndecided: 2026-09-08\ntickets: []\nowner:\n---\n\n# Use queues\n")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        run_maintain(tmp13)
    text = note.read_text()
    check("SKIPPED" not in out.getvalue(), "a note with `tickets: []` is not skipped", out.getvalue())
    check("project: w" in text, "and is maintained", text)
    check("tickets: []\n" in text and "owner:\n" in text, "and keeps its empty values as written", text)
    before = text
    run_maintain(tmp13)
    check(note.read_text() == before, "a second run changes nothing")
finally:
    shutil.rmtree(tmp13, ignore_errors=True)

# ---------------------------------------------------------------------------
section("Hostile input is processed in linear time, and a run cannot hang")
# ---------------------------------------------------------------------------

import time  # noqa: E402


def timed(fn) -> tuple[float, str]:
    out = io.StringIO()
    start = time.monotonic()
    with contextlib.redirect_stdout(out):
        fn()
    return time.monotonic() - start, out.getvalue()


tmp11 = Path(tempfile.mkdtemp())
try:
    ws = tmp11 / "Projects" / "W"
    write(ws / ".vault-config.json", json.dumps({"project": "w", "topics": {
        "queue": {"name": "Queue", "patterns": ["queue"]},
        "bad": {"name": "Bad", "patterns": ["(a+)+$", "("]},
    }}))
    # Each of these took seconds to hours before: a run of blank lines against the task-box and
    # Next/Did patterns, and a run of `[` against the wikilink pattern.
    write(ws / "Threads" / "Blank.md",
          "---\ntype: thread\nstatus: open\n---\n\n# Blank\n" + "\n" * 200_000 + "- [ ] one\n- [x] two\n")
    write(ws / "Notes" / "Brackets.md", "# Brackets\n\n" + "[" * 100_000 + "\n[[Blank]]\n")
    # `(a+)+$` backtracks exponentially on a run of `a` that does not end the text.
    write(ws / "Notes" / "Queue.md", "# Queue\n\nqueue queue queue " + "a" * 40 + "!\n")
    took, out = timed(lambda: run_maintain(tmp11))
    check(took < 3, "a run over pathological notes finishes promptly", f"{took:.1f}s")
    threads = (ws / "ThreadsIndex.md").read_text()
    check("**1 open**" in threads,
          "the open-item count is still right after a long blank run", threads[-400:])
    check("queue" in (ws / "Notes" / "Queue.md").read_text().split("---")[1],
          "a runaway topic pattern does not stop the other topics being derived")
    check("vault-maintain: warning: W: topic 'bad' pattern '(a+)+$'" in out,
          "the runaway pattern is named in a warning line", out)
    check("pattern '('" not in out, "a pattern that does not compile is dropped silently")
    check(vm.link_targets("[[[[a]] [[b|c]] ![[d.png]] [[e#h]]") == ["a", "b", "e"],
          "wikilink targets are unchanged by the linear pattern")
finally:
    shutil.rmtree(tmp11, ignore_errors=True)

tmp12 = Path(tempfile.mkdtemp())
real_all, real_budget = vm.maintain_all, vm.RUN_BUDGET
try:
    (tmp12 / "Projects").mkdir(parents=True)

    def forever(vault: Path) -> list[str]:
        while True:
            time.sleep(0.01)

    vm.maintain_all, vm.RUN_BUDGET = forever, 0.3
    took, out = timed(lambda: run_maintain(tmp12))
    check(took < 2, "a run that never ends is stopped at the budget", f"{took:.1f}s")
    check("vault-maintain: warning: stopped after 0.3s" in out, "and says so in a warning line", out)
finally:
    vm.maintain_all, vm.RUN_BUDGET = real_all, real_budget
    shutil.rmtree(tmp12, ignore_errors=True)

try:
    with vm.time_limit(1.0):
        try:
            with vm.time_limit(0.05, vm.SlowPattern):
                time.sleep(0.5)
            check(False, "an inner limit raises its own exception")
        except vm.SlowPattern:
            check(True, "an inner limit raises its own exception")
        time.sleep(0.1)
    check(True, "the outer limit resumes and does not fire early")
except vm.Overrun:
    check(False, "the outer limit resumes and does not fire early")
try:
    with vm.time_limit(0.1):
        with vm.time_limit(5.0, vm.SlowPattern):
            time.sleep(1)
    check(False, "an inner limit never outlasts the outer one")
except vm.Overrun:
    check(True, "an inner limit never outlasts the outer one")
except vm.SlowPattern:
    check(False, "an inner limit never outlasts the outer one", "the inner one fired")

# ---------------------------------------------------------------------------
print()
if not FAIL:
    print(f"\033[32m{PASS} passed\033[0m")
    sys.exit(0)
print(f"\033[31m{len(FAIL)} failed\033[0m, {PASS} passed")
for n in FAIL:
    print(f"  - {n}")
sys.exit(1)

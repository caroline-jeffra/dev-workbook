#!/usr/bin/env python3
"""Checks behind tests/test-skill-rules.sh: the manage-project-workspaces rule inventory.

Every rule of the v3.5.0 skill must end in exactly one home. tests/skill-rules.tsv names the
home of each rule as `phrase<TAB>expected file[<TAB>flag]` (case-insensitive fixed strings).

Flags:
  (none)    the phrase appears in exactly one file under the skill, and that file is the expected one
  new       text that did not exist in v3.5.0: same check, but only once the split has happened
  home      a rule the target file already owned: same check, only once the split has happened
  pointer   the expected file must contain the phrase (a link); other files may as well
  replaced  the phrase must be gone from every file (the rule was reworded; a `new` row names its home)

Before the split (no --split) only the checks that hold on today's tree run.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(REPO, "skills", "manage-project-workspaces")
TSV = os.path.join(REPO, "tests", "skill-rules.tsv")
TAG = "v3.5.0"
BUDGET = 8192


def read_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            phrase, expected = parts[0], parts[1]
            flag = parts[2] if len(parts) > 2 else ""
            rows.append((phrase, expected, flag))
    return rows


def skill_files(skill):
    out = {}
    for root, _dirs, files in os.walk(skill):
        for name in files:
            p = os.path.join(root, name)
            with open(p, encoding="utf-8") as f:
                out[os.path.relpath(p, skill)] = f.read().lower()
    return out


def check_rules(skill, rows, split):
    fails = []
    files = skill_files(skill)
    for phrase, expected, flag in rows:
        low = phrase.lower()
        holders = sorted(n for n, t in files.items() if low in t)
        if flag == "pointer":
            if split and expected not in holders:
                fails.append(f"pointer missing from {expected}: {phrase}")
        elif flag == "replaced":
            if split and holders:
                fails.append(f"replaced rule still present in {', '.join(holders)}: {phrase}")
        else:
            if flag == "" and len(holders) != 1:
                fails.append(f"phrase must appear in exactly one file, found in {holders or 'none'}: {phrase}")
            elif split and holders != [expected]:
                fails.append(f"phrase belongs only in {expected}, found in {holders or 'none'}: {phrase}")
    return fails


def body_bytes(path):
    with open(path, "rb") as f:
        data = f.read()
    if data.startswith(b"---\n"):
        end = data.find(b"\n---\n", 4)
        if end != -1:
            data = data[end + 5:]
    return len(data)


def git_show(ref_path):
    r = subprocess.run(["git", "-C", REPO, "show", f"{TAG}:{ref_path}"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def frozen_segments(text):
    """The match table, index_notes line, trial rule and Step 1b of a router, by heading range."""
    lines = text.split("\n")
    segs = {}
    for i, ln in enumerate(lines):
        if ln.startswith("| `match` | Do |"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            segs["match table"] = "\n".join(lines[i:j])
        elif ln.startswith("If `index_notes=yes`"):
            segs["index_notes"] = ln
        elif ln.startswith("**Trial workspace.**"):
            j = i
            while j < len(lines) and lines[j].strip():
                j += 1
            segs["trial rule"] = "\n".join(lines[i:j])
        elif ln.startswith("## Step 1b"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("The full contract") \
                    and not lines[j].startswith("## "):
                j += 1
            segs["step 1b"] = "\n".join(lines[i:j]).rstrip("\n")
    return segs


def check_frozen(skill):
    old = git_show("skills/manage-project-workspaces/SKILL.md")
    if old is None:
        return None
    want = frozen_segments(old)
    with open(os.path.join(skill, "SKILL.md"), encoding="utf-8") as f:
        got = frozen_segments(f.read())
    fails = []
    for name in ("match table", "index_notes", "trial rule", "step 1b"):
        if name not in want:
            fails.append(f"{name}: not found in {TAG} (extractor out of date)")
        elif got.get(name) != want[name]:
            fails.append(f"{name} differs from {TAG}")
    return fails


def blocks(text):
    """Paragraph / bullet / table-row blocks of a markdown file; fences are checked separately."""
    out, cur, in_fence = [], [], False

    def flush():
        if cur:
            out.append(" ".join(s.strip() for s in cur))
            cur.clear()

    lines = text.split("\n")
    if lines and lines[0] == "---":
        end = lines.index("---", 1)
        lines = lines[end + 1:]
    for ln in lines:
        if ln.lstrip().startswith("```") or ln.lstrip().startswith("~~~"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not ln.strip() or ln.startswith("#"):
            flush()
        elif ln.startswith("|"):
            flush()
            out.append(ln)
        elif re.match(r"^\s*([-*]|\d+\.)\s", ln):
            flush()
            cur.append(ln)
        elif ln.lstrip().startswith(">"):
            if cur and not cur[0].lstrip().startswith(">"):
                flush()
            cur.append(ln)
        else:
            cur.append(ln)
    flush()
    return [b for b in out if re.search(r"[A-Za-z0-9]", b) and len(b.strip("| -")) >= 20]


def check_orphans(rows):
    old = git_show("skills/manage-project-workspaces/SKILL.md")
    tmpl = git_show("skills/manage-project-workspaces/reference/templates.md")
    if old is None or tmpl is None:
        return None
    sources = {"SKILL.md": old, "templates.md:30-72": "\n".join(tmpl.split("\n")[29:72])}
    phrases = [p.lower() for p, _e, f in rows if f in ("", "home", "replaced")]
    fails = []
    for name, text in sources.items():
        for b in blocks(text):
            if not any(p in b.lower() for p in phrases):
                fails.append(f"{name}: no inventory row covers: {b[:90]}")
    return fails


def fenced(text):
    out, cur, fence = [], [], None
    for ln in text.split("\n"):
        s = ln.lstrip()
        if fence is None and (s.startswith("```") or s.startswith("~~~")):
            fence, cur = s[:3], [ln]
        elif fence is not None:
            cur.append(ln)
            if s.startswith(fence) and len(cur) > 1:
                out.append("\n".join(cur))
                fence, cur = None, []
    return out


def check_fences(skill):
    old = git_show("skills/manage-project-workspaces/SKILL.md")
    if old is None:
        return None
    new = ""
    for root, _d, files in os.walk(skill):
        for name in files:
            with open(os.path.join(root, name), encoding="utf-8") as f:
                new += f.read() + "\n"
    return [f"code block lost: {b.split(chr(10))[1][:70] if b.count(chr(10)) else b}"
            for b in fenced(old) if b not in new]


# ---------------------------------------------------------------------------
# templates: one file per type, split verbatim from v3.5.0's templates.md

TEMPLATE_FILES = {
    "## Index note": "index", "## Overview.md": "overview", "## ProgressLog.md": "progress-log",
    "## Log \u2014": "log", "## Thread \u2014": "thread", "## Playbook \u2014": "playbook",
    "## Research \u2014": "research", "## Ticket \u2014": "ticket", "## Decision \u2014": "decision",
    "## Note \u2014": "note", "## Diagram \u2014": "diagram", "## TimeTracking.md": "time-tracking",
    "## `.vault-config.json`": "vault-config", "## `TasksArchive.md`": "tasks-archive",
}
# Types whose template step 5 changes on purpose: only lines that mention "next" may differ.
NEXT_CHANGED = ("overview", "ticket")


def unfenced_headings(lines, prefix):
    fence, out = None, []
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        m = re.match(r"^(`{3,}|~{3,})", s)
        if m:
            if fence is None:
                fence = m.group(1)
            elif s.startswith(fence):
                fence = None
            continue
        if fence is None and ln.startswith(prefix):
            out.append(i)
    return out


def old_template_sections():
    old = git_show("skills/manage-project-workspaces/reference/templates.md")
    if old is None:
        return None
    lines = old.split("\n")
    heads = [i for i in unfenced_headings(lines, "## ") if lines[i] != "## Contents"]
    subs = unfenced_headings(lines, "### ")
    out = {}
    for k, i in enumerate(heads):
        end = heads[k + 1] if k + 1 < len(heads) else len(lines)
        name = next(v for h, v in TEMPLATE_FILES.items() if lines[i].startswith(h))
        if name == "index":  # the subsections after the table moved to scaffold.md
            end = min([s for s in subs if i < s < end] + [end])
        out[name] = "\n".join(lines[i:end]).rstrip("\n")
    return out


def check_templates(skill):
    want = old_template_sections()
    if want is None:
        return None
    fails = []
    index = os.path.join(skill, "reference", "templates.md")
    with open(index, encoding="utf-8") as f:
        index_text = f.read()
    for name, expect in want.items():
        path = os.path.join(skill, "reference", "templates", name + ".md")
        if not os.path.exists(path):
            fails.append(f"missing template file {name}.md")
            continue
        if f"](templates/{name}.md)" not in index_text:
            fails.append(f"templates.md does not link templates/{name}.md")
        with open(path, encoding="utf-8") as f:
            got = f.read().rstrip("\n").replace("](../", "](")
        if got == expect:
            continue
        if name in NEXT_CHANGED:
            import difflib
            diff = [d for d in difflib.unified_diff(expect.split("\n"), got.split("\n"), lineterm="", n=0)
                    if d[:1] in "+-" and d[:3] not in ("+++", "---")]
            if all("next" in d.lower() for d in diff):
                continue
        fails.append(f"{name}.md differs from the {TAG} section")
    return fails


# ---------------------------------------------------------------------------
# links: every relative link and every named section under skills/ resolves


def slug(heading):
    s = re.sub(r"[`*_]", "", heading).strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def md_headings(path):
    out = []
    fence = None
    with open(path, encoding="utf-8") as f:
        for ln in f:
            s = ln.lstrip()
            m = re.match(r"^(`{3,}|~{3,})", s)
            if m:
                if fence is None:
                    fence = m.group(1)
                elif s.startswith(fence):
                    fence = None
                continue
            if fence is None and ln.startswith("#"):
                out.append(ln.lstrip("#").strip())
    return out


def has_heading(path, ref):
    ref = re.sub(r"[`*]", "", ref).strip().lower()
    return any(re.sub(r"[`*]", "", h).lower().startswith(ref) for h in md_headings(path))


def check_links():
    root = os.path.join(REPO, "skills")
    fails = []
    for dirpath, _d, files in os.walk(root):
        for name in files:
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, REPO)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            # drop fenced blocks and inline code before looking for links
            plain, fence = [], None
            for ln in text.split("\n"):
                s = ln.lstrip()
                m = re.match(r"^(`{3,}|~{3,})", s)
                if m:
                    if fence is None:
                        fence = m.group(1)
                    elif s.startswith(fence):
                        fence = None
                    continue
                if fence is None:
                    plain.append(re.sub(r"`[^`]*`", "``", ln))
            for ln in plain:
                first = None
                for target in re.findall(r"\]\(([^)\s]+)\)", ln):
                    if re.match(r"^[a-z]+:", target):
                        continue
                    file_part, _, anchor = target.partition("#")
                    dest = os.path.normpath(os.path.join(dirpath, file_part)) if file_part else path
                    if not os.path.exists(dest):
                        fails.append(f"{rel}: broken link {target}")
                        continue
                    if first is None and dest.endswith(".md"):
                        first = dest
                    if anchor and dest.endswith(".md"):
                        if anchor not in [slug(h) for h in md_headings(dest)]:
                            fails.append(f"{rel}: no heading for #{anchor} in {os.path.relpath(dest, REPO)}")
                if first is None:
                    continue
                refs = []
                for m in re.finditer(r'"([A-Z][^"]{2,70})" in (?:the )?\[', ln):
                    refs.append(m.group(1))
                for m in re.finditer(r"read ((?:\"[^\"]+\"(?:, | and )?)+) first", ln):
                    refs += re.findall(r'"([^"]+)"', m.group(1))
                for m in re.finditer(r"\(((?:\"[^\"]+\"(?:, | and )?)+)\) (?:are|is) in \[", ln):
                    refs += re.findall(r'"([^"]+)"', m.group(1))
                for ref in refs:
                    if not has_heading(first, ref):
                        fails.append(f"{rel}: no section \"{ref}\" in {os.path.relpath(first, REPO)}")
    # sed instructions: the headings closeout.md and scaffold.md tell the model to print
    structure = os.path.join(SKILL, "reference", "structure.md")
    ref_dir = os.path.join(SKILL, "reference")
    with open(os.path.join(ref_dir, "closeout.md"), encoding="utf-8") as f:
        table = re.findall(r"^\| [^|]+ \| ((?:`[^`|]+`(?:, )?)+) \|$", f.read(), re.M)
    for cell in table:
        for prefix in re.findall(r"`([^`]+)`", cell):
            if prefix.startswith("##") or prefix.startswith("templates/"):
                continue
            if not any(h.lower().startswith(prefix.lower()) for h in md_headings(structure)):
                fails.append(f"closeout.md: sed prefix `{prefix}` matches no heading of structure.md")
    with open(os.path.join(ref_dir, "scaffold.md"), encoding="utf-8") as f:
        for heading in re.findall(r"`## ([A-Z][^`<]+)`", f.read()):
            if not has_heading(structure, heading):
                fails.append(f"scaffold.md: no heading {heading} in structure.md")
    return fails


# ---------------------------------------------------------------------------
# mutation self-test


def sentence_cut(text, phrase):
    """Delete the sentence of `text` that holds `phrase`; return the new text or None."""
    i = text.lower().find(phrase.lower())
    if i == -1:
        return None
    start = max(text.rfind(". ", 0, i) + 2, text.rfind("\n", 0, i) + 1, 0)
    ends = [e for e in (text.find(". ", i + len(phrase)), text.find("\n", i + len(phrase))) if e != -1]
    end = min(ends) + 1 if ends else len(text)
    return text[:start] + text[end:]


def selftest():
    rows = read_rows(TSV)
    fails = []

    def expect_red(label, skill):
        if not check_rules(skill, rows, True):
            fails.append(f"self-test: {label} did not turn the check red")

    # 1. a synthetic tree built from the inventory: green, then one sentence per file removed
    syn = tempfile.mkdtemp()
    try:
        dests = {}
        for phrase, expected, flag in rows:
            if flag == "replaced":
                continue
            dests.setdefault(expected, []).append((phrase, flag))
        for rel, items in dests.items():
            p = os.path.join(syn, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                for phrase, _flag in items:
                    f.write(f"A sentence holding {phrase} for the test.\n")
        if check_rules(syn, rows, True):
            fails.append("self-test: the synthetic tree is not green: " + check_rules(syn, rows, True)[0])
        for rel, items in dests.items():
            real = [ph for ph, fl in items if fl != "pointer"]
            for phrase in real[:1] or [items[0][0]]:
                tmp = tempfile.mkdtemp()
                try:
                    shutil.copytree(syn, tmp, dirs_exist_ok=True)
                    p = os.path.join(tmp, rel)
                    with open(p, encoding="utf-8") as f:
                        cut = sentence_cut(f.read(), phrase)
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(cut)
                    expect_red(f"deleting a sentence from {rel}", tmp)
                finally:
                    shutil.rmtree(tmp)
        # a duplicate home turns it red
        tmp = tempfile.mkdtemp()
        try:
            shutil.copytree(syn, tmp, dirs_exist_ok=True)
            first = next(r for r in rows if r[2] == "")
            other = "SKILL.md" if first[1] != "SKILL.md" else "reference/read.md"
            with open(os.path.join(tmp, other), "a", encoding="utf-8") as f:
                f.write(first[0] + "\n")
            expect_red("copying a rule into a second file", tmp)
        finally:
            shutil.rmtree(tmp)
        # a replaced rule that comes back turns it red
        rep = next((r for r in rows if r[2] == "replaced"), None)
        if rep:
            tmp = tempfile.mkdtemp()
            try:
                shutil.copytree(syn, tmp, dirs_exist_ok=True)
                with open(os.path.join(tmp, "SKILL.md"), "a", encoding="utf-8") as f:
                    f.write(rep[0] + "\n")
                expect_red("restoring a replaced rule", tmp)
            finally:
                shutil.rmtree(tmp)
    finally:
        shutil.rmtree(syn)

    # 2. the real tree, once split: one sentence per destination file
    if os.path.exists(os.path.join(SKILL, "reference", "read.md")) and SPLIT_REAL:
        dests = {}
        for phrase, expected, flag in rows:
            if flag in ("", "new"):
                dests.setdefault(expected, phrase)
        for rel, phrase in dests.items():
            tmp = tempfile.mkdtemp()
            try:
                shutil.copytree(SKILL, tmp, dirs_exist_ok=True)
                p = os.path.join(tmp, rel)
                with open(p, encoding="utf-8") as f:
                    cut = sentence_cut(f.read(), phrase)
                if cut is None:
                    fails.append(f"self-test: {rel} does not hold its own phrase: {phrase}")
                    continue
                with open(p, "w", encoding="utf-8") as f:
                    f.write(cut)
                expect_red(f"deleting a sentence from the real {rel}", tmp)
            finally:
                shutil.rmtree(tmp)
    return fails


SPLIT_REAL = False


def main(argv):
    global SPLIT_REAL
    split = "--split" in argv
    SPLIT_REAL = split
    args = [a for a in argv if not a.startswith("--")]
    cmd = args[0]
    rows = read_rows(TSV)
    if cmd == "rules":
        res = check_rules(SKILL, rows, split)
    elif cmd == "budget":
        n = body_bytes(os.path.join(SKILL, "SKILL.md"))
        res = [] if n <= BUDGET else [f"router body is {n} bytes, budget {BUDGET}"]
    elif cmd == "frozen":
        res = check_frozen(SKILL)
    elif cmd == "orphans":
        res = check_orphans(rows)
    elif cmd == "fences":
        res = check_fences(SKILL)
    elif cmd == "templates":
        res = check_templates(SKILL)
    elif cmd == "links":
        res = check_links()
    elif cmd == "selftest":
        res = selftest()
    else:
        print(f"unknown command {cmd}", file=sys.stderr)
        return 2
    if res is None:
        print(f"SKIP {TAG} is not available in this clone")
        return 0
    for line in res:
        print(line)
    return 1 if res else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

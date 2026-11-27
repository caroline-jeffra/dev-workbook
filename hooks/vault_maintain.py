#!/usr/bin/env python3
"""Maintain a project workspace's derived metadata and indexes.

This is a MAINTENANCE tool, not a migration tool. It runs on every session end
against a workspace that already has the right shape, and it is deliberately
constrained:

  * It NEVER deletes a file, moves a file, or edits a note's body.
  * It only rewrites index notes, the frontmatter of ordinary notes, and the one-line
    `Projects/.dev-workbook-version` record.
  * Every write is compare-before-write, so a no-op run touches nothing.
  * It fails open: any unexpected error exits 0 with a message on stderr, so a
    bug here can never break a session or block the vault push.

What it does, per workspace:
  1. Reads every note's frontmatter.
  2. Fills in derived fields on notes that lack them — `type` (inferred from
     the folder the note is in), `topics` (matched from the workspace's topic
     vocabulary), and the derived `topic/*` / doctype tags.
  3. Regenerates the index notes from what it found.

With `--lint`, it writes nothing at all: it reports every note that breaks the format contract
(skills/manage-project-workspaces/reference/structure.md), one line each, for `condense-vault` to
work through. `--lint --count` prints only the number of findings.

With `--claim`, it only records this plugin's version in the vault (see "Stale-session guard"
below) — the SessionStart hook runs it so the record lands before any older session exits.

A workspace opts in by containing a `.vault-config.json`. Workspaces without
one are ignored entirely, so this is safe to run across a mixed vault where
most projects still use the old flat layout.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

# ---------------------------------------------------------------- frontmatter

FM_START = "---\n"


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (raw_frontmatter, body). Raw is '' when there is none."""
    if not text.startswith(FM_START):
        return "", text
    end = text.find("\n---\n", len(FM_START) - 1)
    if end == -1:
        return "", text
    return text[len(FM_START) : end + 1], text[end + 5 :]


def parse_frontmatter(raw: str) -> dict[str, object]:
    """Minimal YAML-subset parser covering inline lists AND block lists.

    Block lists matter: Obsidian's own property editor writes them, so a parser
    that only understands `[a, b]` silently drops tags the user added by hand.
    """
    out: dict[str, object] = {}
    key: str | None = None
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        block = re.match(r"^\s+-\s*(.*)$", line)
        if block and key:
            out.setdefault(key, [])
            if isinstance(out[key], list):
                out[key].append(_scalar(block.group(1)))
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest == "":
            out[key] = []          # a block list may follow
        elif rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1].strip()
            out[key] = [_scalar(x) for x in _split_inline(inner)] if inner else []
        else:
            out[key] = _scalar(rest)
    return out


def _split_inline(s: str) -> list[str]:
    """Split an inline list on commas that are not inside quotes."""
    parts, buf, quote = [], [], ""
    for ch in s:
        if quote:
            if ch == quote:
                quote = ""
            buf.append(ch)
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


# YAML 1.1 words that must be quoted or they stop being strings.
_YAML_RESERVED = {
    "true", "false", "yes", "no", "on", "off", "null", "none", "~",
    "y", "n",
}


def emit_scalar(value: str) -> str:
    """Quote a scalar whenever an unquoted form would change its meaning."""
    v = str(value)
    if v == "":
        return '""'
    if v.lower() in _YAML_RESERVED:
        return f'"{v}"'
    # A plain integer or decimal is left unquoted — these are real numeric fields
    # (counts, totals) and quoting them would change their type on every run.
    # Anything number-ish but not a clean number (leading zeros, underscores,
    # exponents, versions like 1.2.3) is quoted so it stays a string.
    if re.fullmatch(r"-?\d+(\.\d+)?", v) and not re.fullmatch(r"-?0\d+", v):
        return v
    if re.search(r"[:#\[\]{},&*?|<>=!%@`\"']", v) or v[0] in "-?%@`":
        esc = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    return v


def _normalise_fm(raw: str) -> list[str]:
    """Comparable form of a frontmatter block: non-empty lines, trailing space stripped."""
    return [ln.rstrip() for ln in raw.strip().splitlines() if ln.strip()]


def frontmatter_roundtrips(raw: str) -> bool:
    """True when parse -> emit reproduces this frontmatter without losing anything.

    The parser here is a deliberately small YAML subset, which is fine for reading but
    dangerous for writing: `emit_frontmatter` writes back only what `parse_frontmatter`
    understood, so anything it could not represent is silently deleted from the user's
    file. Nested mappings vanish entirely; `key: |` block scalars keep the key and lose
    the body; comments disappear.

    Rather than grow the parser to cover all of YAML — where the next unhandled shape is
    always one plugin away — we check whether a round trip is faithful and decline to
    rewrite the note when it is not. A note the hook cannot represent is a note the hook
    has no business editing.
    """
    parsed = parse_frontmatter(raw)
    emitted = emit_frontmatter(parsed)
    # emit_frontmatter brackets its output with --- markers; compare only the fields.
    body = emitted.strip()
    if body.startswith("---"):
        body = body[3:]
    if body.endswith("---"):
        body = body[:-3]

    original = _normalise_fm(raw)
    produced = _normalise_fm(body)

    # A block list legitimately re-emits as an inline list, so compare semantically:
    # re-parse what we produced and require the same key/value mapping, AND require that
    # every source line is accounted for by some key we captured.
    if parse_frontmatter(body) != parsed:
        return False

    # Every non-empty source line must belong to a key we understood. A comment, a nested
    # mapping's child, or a block scalar's body will not, and that is the signal.
    known_keys = set(parsed)
    for line in original:
        stripped = line.strip()
        if stripped.startswith("#"):
            return False                       # comments are dropped by the emitter
        if stripped.startswith("- "):
            continue                           # block-list item, represented as a list
        key = line.split(":", 1)[0].strip()
        if line.startswith((" ", "\t")):
            return False                       # indented non-list line: nested structure
        if key not in known_keys:
            return False
        value = line.split(":", 1)[1].strip() if ":" in line else ""
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            return False                       # block scalar: body would be lost
    return True


def emit_frontmatter(fields: dict[str, object]) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, list):
            # Newlines inside a value would produce structurally invalid YAML.
            items = [emit_scalar(str(x).replace("\n", " ")) for x in v]
            lines.append(f"{k}: [{', '.join(items)}]")
        else:
            lines.append(f"{k}: {emit_scalar(str(v).replace(chr(10), ' '))}")
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------- config


# The folder skeleton is fixed by the workspace contract, not configured per workspace:
# every structured workspace uses these names, and the skills rely on that. It stays
# overridable from .vault-config.json only so workspaces written before the contract was
# fixed keep working; new ones omit the key entirely.
DEFAULT_FOLDERS: dict[str, str] = {
    "ticket": "Tickets",
    "epic": "Epics",
    "playbook": "Playbooks",
    "research": "Research",
    "note": "Notes",
    "decision": "Decisions",
    "convention": "Decisions",
    "thread": "Threads",
    "log": "Log",
    "diagram": "Diagrams",
}

# An Excalidraw drawing is a markdown file the Obsidian plugin owns: `Name.excalidraw.md`, its
# labels under `## Text Elements` and the scene in a (usually compressed) JSON block. It is a
# note for naming and linking, but its frontmatter and body are never rewritten or linted.
DRAWING_SUFFIX = ".excalidraw"


def is_drawing(p: Path) -> bool:
    return p.name.endswith(DRAWING_SUFFIX + ".md")


@dataclass
class Config:
    project: str
    folders: dict[str, str]                  # doctype -> folder name
    root_notes: set[str]
    index_types: set[str]
    topics: dict[str, dict]                  # slug -> {name, gloss, patterns}
    generated_types: set[str] = field(default_factory=set)
    min_hits: int = 3
    title_weight: int = 4
    slow: list[str] = field(default_factory=list)   # topic patterns dropped this run for overrunning

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            project=raw["project"],
            # Merged, not replaced: an override for one type must not hide a folder added to the
            # contract after that workspace's config was written (Playbooks/, in 1.2).
            folders={**DEFAULT_FOLDERS, **(raw.get("folders") or {})},
            root_notes=set(raw.get("root_notes", [])),
            index_types=set(raw.get("index_types", [])),
            topics=clean_topics(raw.get("topics", {})),
            generated_types=set(raw.get("generated_types", ["index", "log-index"])),
            min_hits=raw.get("min_hits", 3),
            title_weight=raw.get("title_weight", 4),
        )

    def doctype_for_folder(self, folder: str) -> str | None:
        for doctype, name in self.folders.items():
            if name == folder:
                return doctype
        return None


def clean_topics(topics: object) -> dict[str, dict]:
    """The config's topics, with every name and gloss on one line. The config arrives with the
    vault, so a newline in a gloss must not become a line of its own in a generated index."""
    if not isinstance(topics, dict):
        return {}
    out: dict[str, dict] = {}
    for slug, spec in topics.items():
        if not isinstance(spec, dict):
            continue
        spec = dict(spec)
        for key in ("name", "gloss"):
            if key in spec:
                spec[key] = one_line(spec[key])
        # Compiled once per run, not once per note; a pattern that does not compile is dropped,
        # as a bad pattern in config must not kill the run.
        compiled = []
        for p in spec.get("patterns") or []:
            try:
                compiled.append(re.compile(p, re.I))
            except (re.error, TypeError):
                continue
        spec["compiled"] = compiled
        out[one_line(slug)] = spec
    return out


# ---------------------------------------------------------------- topics


def score_topic(text: str, slug: str, spec: dict, head: str, cfg: Config) -> int:
    """How strongly a note matches one topic. Each pattern gets PATTERN_BUDGET per note: the
    patterns come from config, and one that backtracks without end would otherwise hang the run.
    An overrunning pattern is dropped for the rest of the run and reported."""
    total = 0
    for p in list(spec.get("compiled", [])):
        try:
            with time_limit(PATTERN_BUDGET, SlowPattern):
                total += len(p.findall(text))
                total += cfg.title_weight * len(p.findall(head))
        except SlowPattern:
            spec["compiled"].remove(p)
            cfg.slow.append(f"topic {slug!r} pattern {one_line(p.pattern, 80)!r}")
    return total


def topics_for(cfg: Config, title: str, body: str, limit: int = 6) -> list[str]:
    head = title + "\n" + "\n".join(body.splitlines()[:12])
    text = title + "\n" + body
    scored = [(slug, score_topic(text, slug, spec, head, cfg)) for slug, spec in cfg.topics.items()]
    kept = sorted(
        [(s, n) for s, n in scored if n >= cfg.min_hits],
        key=lambda x: (-x[1], x[0]),
    )
    return sorted(s for s, _ in kept[:limit])


# ---------------------------------------------------------------- time limits

# The whole run's budget. A run over a vault of 1,300 notes takes under half a second; the budget
# is for the run that never ends (a pathological note, a bad topic pattern), which would hold
# session-end's lock, keep that session's push from running and stall the next session start.
RUN_BUDGET = 10.0
# One topic pattern against one note.
PATTERN_BUDGET = 0.25


class Overrun(BaseException):
    """The run's budget ran out. A BaseException, so the fail-open `except Exception` handlers
    around each step cannot swallow it and carry on."""


class SlowPattern(BaseException):
    """One topic pattern overran its budget on one note."""


@contextmanager
def time_limit(seconds: float, exc: type[BaseException] = Overrun) -> Iterator[None]:
    """Raise `exc` inside the block once `seconds` pass. Python checks for signals inside a regex
    match, so this stops a runaway pattern too. Limits nest: an inner one never outlasts the
    outer, which raises its own exception when it is the one that ran out, and resumes on exit.
    A no-op where there is no interval timer (Windows) or off the main thread."""
    if not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread():
        yield
        return
    start = time.monotonic()
    outer = signal.getitimer(signal.ITIMER_REAL)[0]
    mine = not outer or seconds < outer

    def ring(*_: object) -> None:
        raise exc if mine else Overrun

    previous = signal.signal(signal.SIGALRM, ring)
    signal.setitimer(signal.ITIMER_REAL, seconds if mine else outer)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if outer:
            signal.setitimer(signal.ITIMER_REAL, max(outer - (time.monotonic() - start), 0.001))


# ---------------------------------------------------------------- safe writes

CONTROL = re.compile(r"[\x00-\x1f\x7f\u0085\u2028\u2029\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")


def one_line(value: object, limit: int = 0) -> str:
    """Text from a config file or a note, made safe to print on one line: control, separator and
    invisible characters become spaces, and with a limit it is cut to that many characters."""
    text = CONTROL.sub(" ", str(value))
    return text if not limit or len(text) <= limit else text[: limit - 1] + "…"


def write_atomic(path: Path, text: str) -> None:
    """Replace path's content all at once, never through a symlink.

    A symlink can arrive from the vault's remote — git stores them — so writing through one would
    let pulled content point a write anywhere on disk. And a write that dies halfway must not
    leave a truncated note, so the text goes to a temporary file beside it that then replaces it.
    """
    if path.is_symlink():
        raise OSError(f"{path.name} is a symlink — not writing through it")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------- notes


@dataclass
class Note:
    path: Path
    name: str
    meta: dict[str, object]
    body: str
    doctype: str
    raw_fm: str = ""
    topics: list[str] = field(default_factory=list)
    changed: bool = False
    text: str = ""                 # the file as read, to detect an edit made during the run

    @property
    def drawing(self) -> bool:
        return is_drawing(self.path)


# Turns a note into the link target the indexes write for it: the shortest path that names it
# and no other note in the vault.
Refs = Callable[[Note], str]


def as_list(v: object) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if v in (None, ""):
        return []
    return [str(v)]


def collect(root: Path, cfg: Config) -> list[Note]:
    notes: list[Note] = []
    try:
        root_real = root.resolve()
    except OSError:
        return notes
    for p in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        # Never follow a link out of the workspace. rglob traverses symlinked files and
        # directories, so without this the pass will happily rewrite a file elsewhere on
        # disk — Obsidian users symlink shared folders between vaults routinely.
        if p.is_symlink():
            continue
        try:
            if not p.resolve().is_relative_to(root_real):
                continue
        except (OSError, ValueError):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        raw, body = split_frontmatter(text)
        meta = parse_frontmatter(raw)

        declared = str(meta.get("type", "") or "")
        folder = p.parent.name if p.parent != root else ""
        inferred = cfg.doctype_for_folder(folder) if folder else None
        # A declared type wins; otherwise infer from location. Root notes with
        # no declared type are left alone rather than guessed at.
        doctype = declared or inferred or ""
        if is_drawing(p):
            doctype = "diagram"

        notes.append(Note(p, p.stem, meta, body, doctype, raw_fm=raw, text=text))
    return notes


def refresh_metadata(notes: list[Note], cfg: Config) -> list[str]:
    """Fill derived frontmatter. Returns human-readable descriptions of changes."""
    changes: list[str] = []
    # Files this run regenerates wholesale. Touching their frontmatter here as
    # well makes the two writers fight: the builder adds its own fields, this
    # pass strips them as unknown, and every run reports a change forever.
    generated_files = {
        "TopicIndex.md", "TicketsIndex.md",
        "ThreadsIndex.md", "DecisionsIndex.md",
        # Their pre-2.0 names: stale copies awaiting removal by condense-vault, not notes.
        "Topic Index.md", "Tickets Index.md",
        "Threads Index.md", "Decisions Index.md",
    }

    for n in notes:
        if not n.doctype or n.path.name in generated_files or n.drawing:
            continue
        fields = dict(n.meta)
        before = dict(n.meta)

        fields["type"] = n.doctype
        fields["project"] = cfg.project

        # Generated indexes describe the workspace rather than a subject, so they
        # carry no topics. Other non-filed notes (a glossary, a summary) ARE
        # content and keep theirs.
        if n.doctype in cfg.generated_types:
            n.topics = []
            fields.pop("topics", None)
        else:
            existing = as_list(n.meta.get("topics"))
            # Respect a hand-curated topic list; only derive when absent.
            n.topics = existing or topics_for(cfg, n.name, n.body)
            # Drop topics that are no longer in the vocabulary.
            n.topics = [t for t in n.topics if t in cfg.topics]
            if n.topics:
                fields["topics"] = n.topics
            else:
                fields.pop("topics", None)

        # Derived tags are rebuilt from scratch each run so a renamed, merged or
        # retired topic never leaves a stale tag behind. Hand-added tags survive.
        derived = set(cfg.folders) | set(cfg.index_types) | {cfg.project}
        kept = [
            t
            for t in as_list(n.meta.get("tags"))
            if not t.startswith("topic/") and t not in derived
        ]
        tags = sorted(set(kept) | {cfg.project, n.doctype} | {f"topic/{t}" for t in n.topics})
        fields["tags"] = tags

        # T1.4: never rewrite a note whose frontmatter this parser cannot represent.
        # Doing so deletes whatever it did not understand — nested mappings, block
        # scalars, comments — from the user's file, with no backup and no signal.
        # Skipping means the note goes unmaintained, which is strictly better than
        # silently damaged.
        if fields != before and n.raw_fm and not frontmatter_roundtrips(n.raw_fm):
            changes.append(
                f"{n.path.name}: SKIPPED — frontmatter uses YAML this tool cannot "
                f"rewrite safely (nested keys, block scalars or comments); left untouched"
            )
            n.meta = before
            continue

        if fields != before:
            new_text = emit_frontmatter(fields) + "\n\n" + n.body.strip() + "\n"
            try:
                current = n.path.read_text(encoding="utf-8")
            except OSError:
                continue
            # Written since this run read it (the editor, another session): the new text is
            # built from the old body, so writing it would discard that edit. The next run
            # picks the note up again.
            if n.text and current != n.text:
                n.meta = before
                continue
            if new_text != current:
                try:
                    write_atomic(n.path, new_text)
                except OSError:
                    n.meta = before
                    continue
                n.changed = True
                added = sorted(set(fields) - set(before))
                changes.append(
                    f"{n.path.name}: "
                    + (f"added {', '.join(added)}" if added else "updated frontmatter")
                )
        n.meta = fields
    return changes


# ---------------------------------------------------------------- indexes

TYPE_PLURAL = {
    "ticket": ("Ticket", "Tickets"),
    "epic": ("Epic", "Epics"),
    "playbook": ("Playbook", "Playbooks"),
    "research": ("Research", "Research"),
    "note": ("Note", "Notes"),
    "decision": ("Decision", "Decisions"),
    "convention": ("Convention", "Conventions"),
    "thread": ("Thread", "Threads"),
    "log": ("Log day", "Log days"),
    "diagram": ("Diagram", "Diagrams"),
}
TYPE_RANK = {
    "playbook": 0, "research": 1, "diagram": 2, "epic": 3, "ticket": 4, "note": 5,
    "decision": 6, "convention": 7, "thread": 8, "log": 9,
}


def label(doctype: str, n: int) -> str:
    pair = TYPE_PLURAL.get(doctype)
    if not pair:
        return doctype.replace("-", " ").title()
    return pair[1] if n != 1 else pair[0]


# Every generated index carries this marker. Its presence is what licenses an overwrite:
# a file at the same path WITHOUT it was written by someone, not by this tool.
GENERATED_MARKER = "_Generated —"


def write_if_changed(path: Path, content: str) -> bool:
    """Write a generated file, refusing to clobber one this tool did not author.

    T1.6: the index filenames are ordinary names a user may already have used. Overwriting
    a hand-written `TopicIndex.md` destroys it with no backup — and the warning that edits
    are overwritten only appears in the file *after* it has already been overwritten.
    """
    content = content.rstrip() + "\n"
    if path.is_symlink():
        print(
            f"vault-maintain: {path.parent.name}: {path.name} is a symlink — not writing "
            f"through it. Replace it with a regular file or remove it to let the index generate.",
            file=sys.stderr,
        )
        return False
    try:
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing == content:
                return False
            if GENERATED_MARKER not in existing:
                # Name the workspace, not just the file. Index filenames repeat across
                # workspaces, so a bare "ThreadsIndex.md exists" in a multi-workspace run
                # is unattributable — the reader cannot tell which one to go and look at.
                print(
                    f"vault-maintain: {path.parent.name}: {path.name} exists and was not "
                    f"generated by this tool — not overwriting. Move or rename it to let "
                    f"the index generate.",
                    file=sys.stderr,
                )
                return False
    except OSError:
        pass
    try:
        write_atomic(path, content)
    except OSError as exc:
        print(f"vault-maintain: {path.parent.name}: {path.name}: {exc}", file=sys.stderr)
        return False
    return True


def build_topic_index(root: Path, cfg: Config, notes: list[Note], ref: Refs) -> bool:
    by_topic: dict[str, list[Note]] = defaultdict(list)
    for n in notes:
        if n.doctype in cfg.generated_types:
            continue
        for t in n.topics:
            by_topic[t].append(n)

    lines = [
        emit_frontmatter(
            {
                "type": "index",
                "project": cfg.project,
                "tags": ["index", cfg.project],
                "topics_covered": len(by_topic),
            }
        ),
        "",
        "# Topic Index",
        "",
        "Every topic covered in this workspace, A–Z. Follow a topic to the notes "
        "that cover it. A note appears under each of its topics.",
        "",
        "Topics are also `topic/<name>` tags, so Obsidian's tag pane and search "
        "work on them directly.",
        "",
        "_Generated — edits here are overwritten. Change the topic vocabulary in "
        "`.vault-config.json`._",
        "",
    ]

    # A workspace can be structured before it has any topics — a new one starts
    # with an empty vocabulary and grows it. Say so, rather than rendering a
    # heading with nothing under it and looking broken.
    if not by_topic:
        lines += [
            "## No topics yet",
            "",
            "This workspace has no topic vocabulary defined, so there is nothing to index yet.",
            "",
            "Add topics to `.vault-config.json` once three or four notes would share one — "
            "earlier than that and a topic is noise. The next session-end run picks them up and "
            "fills this page in.",
        ]
        return write_if_changed(root / "TopicIndex.md", "\n".join(lines))

    ordered = sorted(by_topic, key=lambda s: cfg.topics[s]["name"].lower())
    letters = sorted({cfg.topics[s]["name"][0].upper() for s in ordered})
    # A standard anchor link, not `[[#A]]`: every viewer resolves `(#a)` against the heading's
    # GitHub-style slug, while a heading-only wikilink is Obsidian's dialect.
    lines.append(" · ".join(f"[{l}](#{l.lower()})" for l in letters))
    lines.append("")

    current = ""
    for slug in ordered:
        spec = cfg.topics[slug]
        letter = spec["name"][0].upper()
        if letter != current:
            current = letter
            lines += [f"## {letter}", ""]

        group = by_topic[slug]
        lines += [f"### {spec['name']}", ""]
        if spec.get("gloss"):
            lines += [f"*{spec['gloss']}*", ""]
        lines += [f"Tag: `#topic/{slug}` — {len(group)} notes", ""]

        buckets: dict[str, list[Note]] = defaultdict(list)
        for n in group:
            buckets[n.doctype].append(n)

        for doctype in sorted(buckets, key=lambda d: TYPE_RANK.get(d, 9)):
            items = sorted(buckets[doctype], key=lambda n: n.name.lower())
            if doctype == "log":
                days = " · ".join(
                    wikilink(ref(n), n.name) for n in sorted(items, key=lambda x: x.name, reverse=True)
                )
                lines += [f"**Log days** ({len(items)}) — {days}", ""]
                continue
            lines += [f"**{label(doctype, len(items))}** ({len(items)})", ""]
            lines += [f"- {wikilink(ref(n), n.name)}" for n in items]
            lines.append("")

    return write_if_changed(root / "TopicIndex.md", "\n".join(lines))


def build_ticket_index(root: Path, cfg: Config, notes: list[Note], ref: Refs) -> bool:
    pattern = re.compile(r"^([A-Z]{2,}-\d+)\b")
    by_ticket: dict[str, list[Note]] = defaultdict(list)
    for n in notes:
        if n.doctype in cfg.generated_types:
            continue
        for t in as_list(n.meta.get("tickets")):
            by_ticket[t].append(n)

    owned: dict[str, Note] = {}
    for n in notes:
        m = pattern.match(n.name)
        key = m.group(1) if m else None
        # A ticket note named `<number>-<Subject>` takes its key from `tickets:`.
        num = re.match(r"^(\d+)-", n.name) if key is None and n.doctype == "ticket" else None
        if num:
            key = next((t for t in as_list(n.meta.get("tickets"))
                        if t.rsplit("-", 1)[-1] == num.group(1)), None)
        if key:
            prev = owned.get(key)
            if prev is None or len(n.name) < len(prev.name):
                owned[key] = n

    lines = [
        emit_frontmatter(
            {"type": "index", "project": cfg.project, "tags": ["index", cfg.project]}
        ),
        "",
        "# Tickets Index",
        "",
        "Every ticket mentioned in this workspace, and the notes that mention it. "
        "A ticket with its own note is shown in bold.",
        "",
        "_Generated — edits here are overwritten._",
        "",
    ]

    def sort_key(t: str) -> tuple:
        digits = re.sub(r"\D", "", t)
        return (-int(digits) if digits else 0, t)

    for t in sorted(by_ticket, key=sort_key):
        uniq = {n.name: n for n in by_ticket[t]}.values()
        group = sorted(uniq, key=lambda n: (TYPE_RANK.get(n.doctype, 9), n.name.lower()))
        own = owned.get(t)
        head = f"**{wikilink(ref(own), t)}**" if own else f"`{t}`"
        refs = [n for n in group if n is not own]
        docs = [n for n in refs if n.doctype != "log"]
        logs = [n for n in refs if n.doctype == "log"]
        bits = [wikilink(ref(n), n.name) for n in docs[:6]]
        if logs:
            bits.append(f"{len(logs)} log day{'s' if len(logs) != 1 else ''}")
        lines.append(f"- {head}" + (" — " + ", ".join(bits) if bits else ""))

    return write_if_changed(root / "TicketsIndex.md", "\n".join(lines))


TABLE_ALIAS = re.compile(r"\[\[[^\[\]\n]*?\\?\|[^\[\]\n]*?\]\]")


def wikilink(ref: str, text: str) -> str:
    """`[[ref]]`, or `[[ref|text]]` when the display text differs from the target."""
    return f"[[{ref}|{text}]]" if text and text != ref else f"[[{ref}]]"


def link(n: Note, ref: Refs) -> str:
    """A wikilink carrying a readable display title.

    Note names are slugs, so a bare `[[slug]]` renders as `acme-1701-natural-sort-ad-approvals`.
    Where the note has a title, use `[[slug|Title]]` so the index reads as prose.
    """
    title = str(n.meta.get("title", "") or "").strip()
    if not title:
        for line in n.body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    return wikilink(ref(n), title or n.name)


# A task box at the start of a line. `[ \t]`, not `\s`: with re.M, `^\s*` lets every line of a
# run of blank lines rescan the rest of the run, which is quadratic in the run's length.
TASK_BOX = re.compile(r"^[ \t]*[-*][ \t]+\[( |x|X)\]", re.M)


def open_items(n: Note) -> int:
    """Count unchecked task boxes in a note's body.

    A thread's whole purpose is the work still outstanding, so the index leads with that
    number. Checked boxes and prose are ignored; a thread with no boxes reports zero.
    """
    return sum(1 for box in TASK_BOX.findall(n.body) if box == " ")


def build_thread_index(root: Path, cfg: Config, notes: list[Note], ref: Refs) -> bool:
    """Threads and active playbooks, open work first.

    This is the file `manage-project-workspaces` reads to answer "what's next", so ordering is
    the feature: work with outstanding items comes first, most-open first, and finished threads
    sink to a separate section. A playbook being executed is the tracker for its work (the
    contract forbids mirroring it into a thread), so an active one is listed with the threads.
    """
    threads = [n for n in notes if n.doctype == "thread"]
    playbooks = [
        n for n in notes
        if n.doctype == "playbook" and str(n.meta.get("status", "")).lower() == "active"
    ]

    live, finished = list(playbooks), []
    for n in threads:
        (finished if str(n.meta.get("status", "")).lower() == "done" else live).append(n)

    live.sort(key=lambda n: (-open_items(n), n.name.lower()))
    finished.sort(key=lambda n: n.name.lower())

    lines = [
        emit_frontmatter(
            {"type": "index", "project": cfg.project, "tags": ["index", cfg.project]}
        ),
        "",
        "# Threads Index",
        "",
        "Every thread of unfinished work and active playbook, most open items first.",
        "",
        "_Generated — edits here are overwritten._",
        "",
    ]

    if not threads and not playbooks:
        lines.append("_No threads yet._")
        return write_if_changed(root / "ThreadsIndex.md", "\n".join(lines))

    if live:
        lines.append("## Open")
        lines.append("")
        for n in live:
            count = open_items(n)
            head = f"**{count} open**" if count else f"_{n.meta.get('status', 'open')}_"
            kind = " _(playbook)_" if n.doctype == "playbook" else ""
            lines.append(f"- {head} — {link(n, ref)}{kind}")
        lines.append("")

    if finished:
        lines.append("## Closed")
        lines.append("")
        lines += [f"- {link(n, ref)}" for n in finished]
        lines.append("")

    return write_if_changed(root / "ThreadsIndex.md", "\n".join(lines))


def build_decision_index(root: Path, cfg: Config, notes: list[Note], ref: Refs) -> bool:
    """Decisions and conventions, grouped by whether they are still in force.

    Superseded decisions are listed, never hidden: the record of what was true before is
    what stops a stale claim being read as current.
    """
    items = [n for n in notes if n.doctype in ("decision", "convention")]


    lines = [
        emit_frontmatter(
            {"type": "index", "project": cfg.project, "tags": ["index", cfg.project]}
        ),
        "",
        "# Decisions Index",
        "",
        "Every decision and standing convention, grouped by status.",
        "",
        "_Generated — edits here are overwritten._",
        "",
    ]

    if not items:
        lines.append("_No decisions recorded yet._")
        return write_if_changed(root / "DecisionsIndex.md", "\n".join(lines))

    decisions = [n for n in items if n.doctype == "decision"]
    conventions = [n for n in items if n.doctype == "convention"]

    def when(n: Note) -> str:
        for key in ("decided", "date", "created"):
            v = n.meta.get(key)
            if v:
                return str(v)[:10]
        return ""

    if decisions:
        lines.append("## Dated decisions")
        lines.append("")
        # Newest first; undated decisions sort to the end rather than pretending to a date.
        for n in sorted(decisions, key=lambda n: (when(n) == "", when(n)), reverse=True):
            d = when(n)
            stamp = f"`{d}` " if d else ""
            tail = " _(superseded)_" if str(n.meta.get("status", "")).lower() == "superseded" else ""
            # The tickets a decision came out of are context its title does not carry, and
            # the only link back to the work that prompted it.
            tickets = as_list(n.meta.get("tickets"))
            refs = f" · {', '.join(tickets)}" if tickets else ""
            lines.append(f"- {stamp}{link(n, ref)}{tail}{refs}")
        lines.append("")

    if conventions:
        lines.append("## Standing conventions")
        lines.append("")
        for n in sorted(conventions, key=lambda n: n.name.lower()):
            tail = " _(superseded)_" if str(n.meta.get("status", "")).lower() == "superseded" else ""
            lines.append(f"- {link(n, ref)}{tail}")
        lines.append("")

    return write_if_changed(root / "DecisionsIndex.md", "\n".join(lines))


# ---------------------------------------------------------------- lint
#
# Report-only: lint never writes. It checks notes against the format contract in
# skills/manage-project-workspaces/reference/structure.md, and `condense-vault` works through
# what it finds. Every check is a heuristic tuned to say nothing on a note that follows its
# template — a noisy lint gets ignored, which is worse than none.

ROOT_FILES = {
    "Overview", "ProgressLog", "TopicIndex", "TicketsIndex", "DecisionsIndex", "ThreadsIndex",
    "TimeTracking",
}
INDEX_NAMES = {"TopicIndex", "TicketsIndex", "DecisionsIndex", "ThreadsIndex"}

# Pre-2.0 names of the structural files. A generated one is simply stale (its replacement is
# regenerated beside it); a hand-written one is renamed.
LEGACY_ROOT = {
    "Progress Log": "ProgressLog", "Topic Index": "TopicIndex", "Tickets Index": "TicketsIndex",
    "Decisions Index": "DecisionsIndex", "Threads Index": "ThreadsIndex",
    "Time Tracking": "TimeTracking",
}

# Body words, excluding frontmatter and fenced code. Types not listed have no budget.
BUDGETS = {
    "log": 150, "decision": 150, "convention": 150, "overview": 200, "ticket": 250,
    "thread": 300,
}

# Notes that state current truth. Logs are history; indexes are generated.
CURRENT_STATE = {
    "overview", "thread", "playbook", "decision", "convention", "research", "note", "ticket",
    "epic", "diagram",
}

RESEARCH_KINDS = ("Audit", "Analysis", "Plan", "Spec", "Review", "Map", "Reference")

# PascalCase with acronyms written as words: `AdminApiAudit`, never `AdminAPIAudit`. Three
# capitals in a row is the tell of an acronym kept upper-case; two can be a one-letter word
# (`PlanAForHosting`).
PASCAL = re.compile(r"^(?:[A-Z][a-z0-9]*)+$")
ACRONYM = re.compile(r"[A-Z]{3,}")
# A date in a name, hyphenated or run together as PascalCase leaves it (`Review20261002`).
DATE = re.compile(r"\d{4}-\d{2}-\d{2}|(?:19|20)\d{2}[01]\d[0-3]\d")
LOG_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# The ticket's number and subject. The project key is implicit in the folder, and stays in
# the note's `tickets:` frontmatter.
TICKET_NAME = re.compile(r"^\d+-(?:[A-Z][a-z0-9]*)+$")
# The pre-3.3 form, `ACME-1234-Subject`: every name in a folder began with the same key.
KEYED_TICKET_NAME = re.compile(r"^[A-Z][A-Z0-9]+-\d+-")
# A bare ticket ID as a link target. These are deliberate placeholders for a ticket with no
# note yet (the Tickets Index lists them), not broken links.
TICKET_ID = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
# A link target never holds a bracket, so the inner class excludes `[` as well as `]`: without
# that, a long run of `[` costs quadratic time (each one rescans the rest of the line).
WIKILINK = re.compile(r"(!?)\[\[([^\[\]\n]+)\]\]")
NEXT_LINE = re.compile(r"^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?Next\b\s*:?(?:\*\*)?\s*:?", re.I | re.M)
DID_LINE = re.compile(r"^[ \t]*[-*][ \t]+\*\*Did\b", re.M)
SUBHEADING = re.compile(r"^#{2,6}\s", re.M)
# A line that cannot be the second half of a hard-wrapped paragraph: blank, or the start of
# some other block (heading, list item, quote, table, callout, HTML, embed, indent).
BLOCK_START = re.compile(r"^(\s*$|\s|#|[-*+]\s|\d+[.)]\s|>|\||<|!\[|\[\^|---|\*\*\*)")


def strip_code(body: str) -> str:
    """The body with fenced code blocks and inline code removed — they are not prose."""
    out, fence = [], None
    for line in body.splitlines():
        m = re.match(r"^\s*(`{3,}|~{3,})", line)
        if m:
            if fence is None:
                fence = m.group(1)[0]
            elif m.group(1)[0] == fence:
                fence = None
            continue
        if fence is None:
            out.append(re.sub(r"`[^`\n]*`", "", line))
    return "\n".join(out)


def link_targets(text: str) -> list[str]:
    """Wikilink targets in prose: `[[a|b]]`, `[[a\\|b]]` and `[[a#h]]` all yield `a`.

    Embeds of non-markdown files (`![[diagram.png]]`) are skipped — they are attachments, not
    notes, and the vault's attachment folder is not ours to check.
    """
    found = []
    for embed, inner in WIKILINK.findall(text):
        target = re.split(r"\\?\||#", inner, maxsplit=1)[0].strip()
        if not target:
            continue
        suffix = Path(target).suffix.lower()
        if suffix and suffix not in (".md", DRAWING_SUFFIX) and (embed or len(suffix) <= 5):
            continue
        found.append(target[:-3] if target.endswith(".md") else target)
    return found


KEY_LINE = re.compile(r"^\*\*[^*\n]+:\*\*")


def stacked_keys(prose: str) -> int:
    """Count `**Key:** value` lines sitting directly under another one.

    Obsidian shows each on its own line; CommonMark viewers (Foam, GitHub) join a run of them
    into one paragraph. A blank line between them, or a list item each, reads right everywhere.
    """
    lines = prose.splitlines()
    return sum(1 for a, b in zip(lines, lines[1:]) if KEY_LINE.match(a) and KEY_LINE.match(b))


def hard_wraps(prose: str) -> int:
    """Count places a sentence is broken across two source lines.

    Obsidian renders a single newline as a line break, so consecutive prose lines are not by
    themselves a fault — stacked `**Key:** value` lines are `stacked_keys`' concern. A hard wrap
    is the narrower case of a line that stops mid-sentence and a next line that carries on in
    lowercase.
    """
    count, prev = 0, ""
    for line in prose.splitlines():
        if (
            prev
            and not BLOCK_START.match(line)
            and re.match(r"^[a-z(]", line)
            and not re.search(r"[.!?:;]\W*$", prev)
        ):
            count += 1
        prev = "" if BLOCK_START.match(line) and not line.startswith(("- ", "* ", "> ")) else line.rstrip()
        if not prev.strip():
            prev = ""
    return count


@dataclass
class VaultNames:
    """Every markdown note in the vault, for resolving links across workspaces.

    Resolution follows the rule every wikilink tool shares (Obsidian, Foam, Quartz, Markdown
    Oxide): a target names the notes whose vault-relative path ends with it, compared
    case-insensitively. One match resolves; two or more is ambiguous, and what an ambiguous link
    binds to differs by tool — Obsidian's own tie-break picks one silently.
    """
    stems: dict[str, list[str]]              # stem -> vault-relative paths holding it
    paths: set[str]                          # vault-relative, no `.md`
    suffixes: Counter = field(default_factory=Counter)   # lower-cased path suffix -> notes ending so

    @classmethod
    def scan(cls, vault: Path) -> "VaultNames":
        stems: dict[str, list[str]] = defaultdict(list)
        paths: set[str] = set()
        for p in sorted(vault.rglob("*.md")):
            rel = p.relative_to(vault)
            if any(part.startswith(".") for part in rel.parts):
                continue
            stems[p.stem].append(rel.as_posix())
            paths.add(rel.with_suffix("").as_posix())
        return cls(dict(stems), paths, suffix_counts(paths))

    def matches(self, target: str) -> int:
        """How many notes a link target names."""
        return self.suffixes.get(target.strip("/").lower(), 0)

    def spans_workspaces(self, stem: str) -> bool:
        """Whether notes of this name sit in more than one workspace — allowed, but a bare link
        to the name is then ambiguous."""
        hits = [p for s, ps in self.stems.items() if s.lower() == stem.lower() for p in ps]
        return len({w for w in map(workspace_of, hits) if w}) > 1

    def resolves(self, target: str) -> bool:
        """Whether a link target names some note — bare by stem, or by a trailing path."""
        return self.matches(target) > 0

    def ref(self, path: Path, vault: Path) -> str:
        """The shortest link target that names this note and no other."""
        return shortest_ref(path.relative_to(vault).with_suffix("").as_posix(), self.suffixes)


def suffix_counts(paths) -> Counter:
    """For every note path, count each of its trailing path segments (`a/b/c` -> `c`, `b/c`, `a/b/c`)."""
    counts: Counter = Counter()
    for p in paths:
        parts = p.lower().split("/")
        for i in range(len(parts)):
            counts["/".join(parts[i:])] += 1
    return counts


def shortest_ref(rel: str, suffixes: Counter) -> str:
    """The shortest trailing part of `rel` (vault-relative, no `.md`) that names only that note."""
    parts = rel.split("/")
    for i in range(len(parts) - 1, -1, -1):
        cand = "/".join(parts[i:])
        if suffixes.get(cand.lower(), 0) <= 1:
            return cand
    return rel


def pascal_problem(name: str) -> str | None:
    """Why a name is not PascalCase-with-acronyms-as-words, or None if it is."""
    if not PASCAL.match(name):
        return "name must be PascalCase — no spaces, hyphens, underscores or dashes"
    if ACRONYM.search(name):
        return "write acronyms as words — `ApiAudit`, not `APIAudit`"
    return None


def workspace_of(rel: str) -> str | None:
    """The workspace folder a vault-relative path sits in, or None outside `Projects/<name>/`."""
    parts = rel.split("/")
    return parts[1] if len(parts) > 2 and parts[0] == "Projects" else None


def name_problem(n: Note, workspace: str = "", diagrams: str = "Diagrams") -> str | None:
    name, t = n.name, n.doctype
    if n.drawing:
        name = name[: -len(DRAWING_SUFFIX)]
        if n.path.parent.name != diagrams:
            return f"drawings live in {diagrams}/ — move it there"
    if t == "log":
        return None if LOG_NAME.match(name) else "log name must be YYYY-MM-DD"
    if DATE.search(name):
        return "date in name — dates belong in frontmatter"
    if t == "ticket":
        if TICKET_NAME.match(name) and not ACRONYM.search(name.split("-", 1)[-1]):
            return None
        if KEYED_TICKET_NAME.match(name):
            return "drop the project key — name it '<number>-<Subject>'; the key stays in tickets:"
        return "ticket name must be '<number>-<PascalCaseSubject>'"
    problem = pascal_problem(name)
    if problem:
        return problem
    # The folder already says which project a note belongs to; repeating it pushes the subject
    # out of sight in a sorted or truncated file list.
    w = len(workspace)
    if w and len(name) > w and name[:w].lower() == workspace.lower() and not name[w].islower():
        return f"drop the project name — the {workspace}/ folder already says it"
    if t in ("decision", "convention") and len(re.findall(r"[A-Z]", name)) > 10:
        return "decision name longer than ~10 words — name the claim, not the sentence"
    if t == "research" and not name.endswith(RESEARCH_KINDS):
        return "research name must end in its kind: " + ", ".join(RESEARCH_KINDS)
    if t == "playbook" and name.endswith("Playbook") and name != "Playbook":
        return "drop the 'Playbook' suffix — the Playbooks/ folder already says it"
    return None


def missing_sections(n: Note) -> list[str]:
    body = n.body
    want: list[tuple[str, str]] = []
    if n.doctype == "overview":
        want = [(r"^##\s+Next up\b", "## Next up")]
    elif n.doctype == "research":
        want = [(r"^##\s+TL;?DR\b", "## TL;DR")]
    elif n.doctype == "time-tracking":
        want = [(r"^##\s+Phases\b", "## Phases")]
    elif n.doctype == "playbook":
        want = [
            (r"^\*\*Goal:\*\*", "**Goal:**"),
            (r"^\*\*Done when:\*\*", "**Done when:**"),
            (r"^##\s+Steps\b", "## Steps"),
        ]
    return [label for pat, label in want if not re.search(pat, body, re.M | re.I)]


def lint(root: Path, cfg: Config, notes: list[Note], names: VaultNames, vault: Path) -> list[str]:
    """Every way the workspace breaks its note-format contract, one line per note and problem."""
    out: list[str] = []
    by_name = {n.name: n for n in notes}

    def report(n: Note, code: str, detail: str) -> None:
        out.append(f"{n.path.relative_to(vault).as_posix()}: {code} — {detail}")

    for n in sorted(notes, key=lambda n: n.path):
        stray = False
        if n.path.parent == root:
            if n.name in LEGACY_ROOT:
                new = LEGACY_ROOT[n.name]
                if GENERATED_MARKER in n.body:
                    report(n, "legacy-name", f"pre-2.0 generated index — delete it; it is regenerated as {new}.md")
                else:
                    report(n, "legacy-name", f"pre-2.0 name — rename to {new}.md and update links")
                continue
            if n.name not in ROOT_FILES and n.path.name not in cfg.root_notes:
                stray = True
                report(n, "root-stray", "only the contract files belong in a workspace root")
            if n.name in INDEX_NAMES:
                continue                     # generated; nothing else to check

        status = str(n.meta.get("status", "") or "").lower()
        prose = strip_code(n.body)

        problem = None if stray else name_problem(n, root.name, cfg.folders.get("diagram", "Diagrams"))
        if problem:
            report(n, "bad-name", problem)

        if n.doctype == "thread":
            boxes = TASK_BOX.findall(n.body)
            if status == "done" and boxes:
                report(n, "unclosed-thread", "done thread still holds its item list — reduce it to the closing stub")
            elif status != "done" and boxes and " " not in boxes:
                report(n, "unclosed-thread", f"all {len(boxes)} items ticked — close the thread")

        if n.doctype == "time-tracking":
            words = sum(
                len(line.split()) for line in prose.splitlines()
                if not line.lstrip().startswith(("|", "#"))
            )
            if words > 60:
                report(n, "over-budget", f"{words} words outside the tables (budget 60) — link the detail instead")

        # Logs share date names across workspaces by design, the root files exist once per
        # workspace by design, and a stray is already reported — moving it settles its name.
        if n.doctype != "log" and n.name not in ROOT_FILES and not stray:
            mine = n.path.relative_to(vault).as_posix()
            # Workspaces may share a name — links between them are qualified with the
            # workspace path. A clash inside one workspace, or with a note outside every
            # workspace, still makes a bare link ambiguous where it is meant to be the default.
            here = workspace_of(mine)
            others = [
                p for p in names.stems.get(n.name, [])
                if p != mine and not (here and workspace_of(p) and workspace_of(p) != here)
            ]
            if others:
                report(n, "dup-name", "also at " + ", ".join(others[:3])
                       + (f" (+{len(others) - 3} more)" if len(others) > 3 else ""))

        # The Excalidraw plugin writes the rest of a drawing; only its name and place are ours.
        if n.drawing:
            continue

        budget = BUDGETS.get(n.doctype)
        if budget:
            words = len(prose.split())
            if words > budget:
                report(n, "over-budget", f"{words} words (budget {budget})")

        for label in missing_sections(n):
            report(n, "missing-section", f"no {label}")

        if n.doctype == "log":
            nexts = len(NEXT_LINE.findall(prose))
            if nexts:
                report(n, "log-next", f"{nexts} Next line(s) — next work belongs in the ticket note or the Overview")
            blocks = len(DID_LINE.findall(prose))
            subs = len(SUBHEADING.findall(prose))
            if blocks > 1 or subs:
                report(n, "log-stacked", f"{max(blocks, 1)} Did block(s), {subs} sub-heading(s) — merge into one block")

        targets = link_targets(prose)

        broken = sorted({
            t for t in targets if not TICKET_ID.match(t) and not names.resolves(t)
        })
        # Supersession is recorded in frontmatter, not as a link, so a rename that only
        # rewrites [[links]] leaves these pointing at a name that no longer exists.
        for key in ("supersedes", "superseded_by"):
            for ref in as_list(n.meta.get(key)):
                ref = ref.strip().strip("[]")
                if ref and not names.resolves(ref):
                    report(n, "broken-link", f"frontmatter {key}: {ref} — no note has that name")
        # A link that names several notes binds to whichever one the viewer picks — Obsidian
        # silently picks one, Foam asks. Only names that repeat by design are reported here: a
        # log date or a structural file. Any other repeated name is a dup-name finding, and
        # renaming the duplicate settles every link to it at once.
        ambiguous = sorted({
            t for t in targets
            if names.matches(t) > 1
            and (LOG_NAME.match(t.split("/")[-1]) or t.split("/")[-1] in ROOT_FILES
                 or names.spans_workspaces(t.split("/")[-1]))
        })
        if ambiguous:
            report(n, "ambiguous-link", ", ".join(f"[[{t}]]" for t in ambiguous[:5])
                   + (f" (+{len(ambiguous) - 5} more)" if len(ambiguous) > 5 else "")
                   + " — each names a note in more than one workspace; qualify it with its workspace path "
                   "(scripts/qualify_links.py does this)")
        if broken:
            report(n, "broken-link", ", ".join(f"[[{t}]]" for t in broken[:5])
                   + (f" (+{len(broken) - 5} more)" if len(broken) > 5 else ""))

        if n.doctype in CURRENT_STATE and n.doctype != "overview":
            idx = sorted({
                t for t in targets
                if t.split("/")[-1] in INDEX_NAMES or LEGACY_ROOT.get(t.split("/")[-1]) in INDEX_NAMES
            })
            if idx:
                report(n, "index-link", ", ".join(f"[[{t}]]" for t in idx)
                       + " — link the specific note instead")

        # A rule that is no longer true must not be cited as current from anywhere. Finished
        # work is different: a decision or note linking the thread it came out of is provenance.
        # Only the notes that say what is happening NOW — the overview, and live threads and
        # playbooks — must not point at finished work.
        if n.doctype in CURRENT_STATE and status not in ("superseded", "done"):
            supersedes = set(as_list(n.meta.get("supersedes")))
            tracks_now = n.doctype in ("overview", "thread", "playbook")
            stale = []
            for t in sorted(set(targets)):
                target = by_name.get(t.split("/")[-1])
                if target is None or target is n:
                    continue
                tstatus = str(target.meta.get("status", "") or "").lower()
                if target.doctype in ("decision", "convention") and tstatus == "superseded":
                    if target.name not in supersedes:
                        stale.append(f"[[{t}]] (superseded)")
                elif tracks_now and target.doctype in ("thread", "playbook") and tstatus == "done":
                    stale.append(f"[[{t}]] (done)")
            if stale:
                report(n, "stale-link", ", ".join(stale))

        # An alias pipe inside a table cell splits the row into phantom columns unless escaped,
        # and only some viewers honour the `\\|` escape. Write the link unaliased in a cell.
        aliased = sum(len(TABLE_ALIAS.findall(line)) for line in prose.split("\n")
                      if line.lstrip().startswith("|"))
        if aliased:
            report(n, "table-alias", f"{aliased} aliased link(s) in table cells — drop the alias")

        stacked = stacked_keys(prose)
        if stacked:
            report(n, "stacked-keys", f"{stacked} `**Key:**` line(s) directly under another — "
                   "make each a list item or separate them with a blank line")

        wraps = hard_wraps(prose)
        if wraps:
            report(n, "hard-wrap", f"{wraps} wrapped line(s) — one line per block")

    return out


# ---------------------------------------------------------------- stale-session guard
#
# Hooks are loaded when a session starts, so a session begun before a plugin upgrade still runs
# the old hooks when it exits, and an old maintainer regenerates indexes in the old format. The
# vault therefore records the newest plugin version that has touched it, in a file under
# Projects/ so the session commit syncs it to every machine, and a maintainer older than that
# record does nothing. Versions that cannot be read disable the guard rather than the maintainer.

VERSION_FILE = Path("Projects") / ".dev-workbook-version"
LEGACY_VERSION_FILE = Path("Projects") / ".claudesidion-version"   # read, never written


def parse_version(text: str | None) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"\s*v?(\d+)\.(\d+)\.(\d+)\s*", text or "")
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def own_version() -> str | None:
    manifest = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
    try:
        version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if parse_version(version) else None


def recorded_version(vault: Path) -> str | None:
    """The newest version recorded under either the current or the pre-3.0 file name."""
    found = []
    for rel in (VERSION_FILE, LEGACY_VERSION_FILE):
        path = vault / rel
        if path.is_symlink() or path.parent.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if parse_version(text):
            found.append(text)
    return max(found, key=parse_version, default=None)


def newer_recorded(vault: Path, mine: str | None) -> str | None:
    """The recorded version when it is newer than this plugin's, else None."""
    rec = recorded_version(vault)
    if mine and rec and parse_version(rec) > parse_version(mine):
        return rec
    return None


def claim(vault: Path, mine: str | None) -> None:
    """Record this plugin's version unless a newer one is already recorded.

    Only into an existing Projects/ — creating that folder is the skills' call, behind consent.
    """
    projects = vault / "Projects"
    if not mine or projects.is_symlink() or not projects.is_dir():
        return
    rec = recorded_version(vault)
    if rec is None or parse_version(mine) > parse_version(rec):
        write_atomic(vault / VERSION_FILE, mine + "\n")


# ---------------------------------------------------------------- main


def maintain(root: Path, names: VaultNames | None = None, vault: Path | None = None) -> list[str]:
    """Refresh one workspace. `names` is the whole vault's, so generated links stay unambiguous
    across workspaces; without it the workspace is treated as the whole vault."""
    cfg_path = root / ".vault-config.json"
    if not cfg_path.is_file():
        return []
    cfg = Config.load(cfg_path)

    notes = collect(root, cfg)
    if not notes:
        return []

    if names is None or vault is None:
        vault, names = root, VaultNames.scan(root)

    def ref(n: Note) -> str:
        return names.ref(n.path, vault)

    messages = refresh_metadata(notes, cfg)
    messages += [f"warning: {p} took over {PATTERN_BUDGET:g}s on one note and was skipped" for p in cfg.slow]
    if build_topic_index(root, cfg, notes, ref):
        messages.append("TopicIndex.md regenerated")
    if build_ticket_index(root, cfg, notes, ref):
        messages.append("TicketsIndex.md regenerated")
    if build_thread_index(root, cfg, notes, ref):
        messages.append("ThreadsIndex.md regenerated")
    if build_decision_index(root, cfg, notes, ref):
        messages.append("DecisionsIndex.md regenerated")
    return messages


# How deep to look for workspaces. `Projects/<name>/` is depth 2 and the documented layout;
# the extra levels cover a vault organised by client or team, and the root covers a vault that
# is itself a single workspace. Bounded so a vault with a large attachment tree is not walked
# in full on every session start.
MAX_WORKSPACE_DEPTH = 4


def find_workspaces(vault: Path) -> list[Path]:
    """Every directory holding a .vault-config.json, from the vault root down.

    Walks rather than globbing one depth: a config at the root, at depth 1, or nested under an
    organising folder was previously ignored in silence, which looks exactly like the hook
    being broken. Dot-directories are skipped — `.git` and `.obsidian` are not workspaces, and
    the old `*/*/` glob happily matched `.git/hooks/.vault-config.json`.

    A workspace found inside another is still reported: its config is an explicit statement
    that it is a workspace, and `collect()` scopes each one to its own tree.
    """
    found: list[Path] = []

    def walk(d: Path, depth: int) -> None:
        if (d / ".vault-config.json").is_file():
            found.append(d)
        if depth >= MAX_WORKSPACE_DEPTH:
            return
        try:
            entries = sorted(d.iterdir())
        except OSError:
            return
        for child in entries:
            if child.name.startswith("."):
                continue
            # is_dir() follows symlinks; a link out of the vault is not ours to maintain.
            if child.is_symlink() or not child.is_dir():
                continue
            walk(child, depth + 1)

    walk(vault, 0)
    return sorted(found)


# Pre-2.0 names of the plugin's vault-level notes.
LEGACY_VAULT = {
    "Projects/_index.md": "Projects/WorkspaceIndex.md",
    "Tasks Archive.md": "TasksArchive.md",
    "Work Planning.md": "WorkPlanning.md",
}


def lint_vault_level(vault: Path, workspaces: list[Path]) -> list[str]:
    """Naming outside the workspaces: every note in the vault is PascalCase, and so are the
    workspace folders. `Archived/` is expendable by design and is not checked; `HouseStyles/`
    belongs to clean-docs, whose profile.json names its templates by file, so a rename breaks it."""
    out: list[str] = []
    for ws in workspaces:
        if ws != vault:
            problem = pascal_problem(ws.name)
            if problem:
                out.append(f"{ws.relative_to(vault).as_posix()}/: bad-name — workspace folder: {problem}"
                           " (rename it, its WorkspaceIndex row, its Contributions note and links)")
    for p in sorted(vault.rglob("*.md")):
        rel = p.relative_to(vault)
        if any(part.startswith(".") for part in rel.parts) or rel.parts[0] in ("Archived", "HouseStyles"):
            continue
        if any(p.is_relative_to(ws) for ws in workspaces):
            continue
        key = rel.as_posix()
        if key in LEGACY_VAULT:
            out.append(f"{key}: legacy-name — pre-2.0 name — rename to {LEGACY_VAULT[key]} and update links")
            continue
        if LOG_NAME.match(p.stem):
            continue
        problem = pascal_problem(p.stem.removesuffix(DRAWING_SUFFIX))
        if problem:
            out.append(f"{key}: bad-name — {problem}")
    return out


def run_lint(vault: Path, count_only: bool) -> int:
    names = VaultNames.scan(vault)
    workspaces = find_workspaces(vault)
    findings: list[str] = []
    for ws in workspaces:
        try:
            cfg = Config.load(ws / ".vault-config.json")
            findings += lint(ws, cfg, collect(ws, cfg), names, vault)
        except Exception as exc:                       # noqa: BLE001 - fail open
            print(f"vault-lint: {ws.name}: {exc}", file=sys.stderr)
    try:
        findings += lint_vault_level(vault, workspaces)
    except Exception as exc:                           # noqa: BLE001 - fail open
        print(f"vault-lint: vault level: {exc}", file=sys.stderr)
    if count_only:
        print(len(findings))
    else:
        # Findings quote link targets and names from the notes, which arrive with the vault:
        # one line each, and never a paragraph of someone else's text.
        for f in findings:
            print(one_line(f, 400))
        print(f"vault-lint: {len(findings)} finding(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    lint_mode = "--lint" in args
    count_only = "--count" in args
    paths = [a for a in args if not a.startswith("--")]
    vault = Path(paths[0]) if paths else None
    if vault is None or not vault.is_dir():
        print("usage: vault_maintain.py [--lint [--count] | --claim] <vault-path>", file=sys.stderr)
        return 0                      # fail open

    if not lint_mode:
        mine = own_version()
        newer = newer_recorded(vault, mine)
        if newer:
            print(f"dev-workbook {newer} has already updated this vault, but this session runs "
                  f"{mine}; index maintenance is off until this plugin is updated "
                  "(/plugin marketplace update dev-workbook, then /reload-plugins).")
            return 0
        try:
            claim(vault, mine)
        except OSError as exc:
            print(f"vault-maintain: could not record version: {exc}", file=sys.stderr)
        if "--claim" in args:
            return 0

    if lint_mode:
        try:
            with time_limit(RUN_BUDGET):
                return run_lint(vault, count_only)
        except Overrun:
            print(f"vault-lint: stopped after {RUN_BUDGET:g}s", file=sys.stderr)
            return 0
        except Exception as exc:                       # noqa: BLE001 - fail open
            print(f"vault-lint: {exc}", file=sys.stderr)
            return 0

    total: list[str] = []
    try:
        with time_limit(RUN_BUDGET):
            total = maintain_all(vault)
    except Overrun:
        # Every write is atomic, so stopping part-way leaves each note either old or new. Lines
        # starting `vault-maintain: warning:` are relayed to the next session start.
        print(f"vault-maintain: warning: stopped after {RUN_BUDGET:g}s, so some indexes may be "
              "stale; a vault note or topic pattern is unusually slow to process")
    except Exception as exc:                           # noqa: BLE001 - fail open
        print(f"vault-maintain: {exc}", file=sys.stderr)

    warnings = [m for m in total if ": warning: " in m]
    for m in warnings:
        print("vault-maintain: warning: " + one_line(m.replace("warning: ", "", 1), 400))
    rest = [m for m in total if m not in warnings]
    if rest:
        print(f"vault-maintain: {len(rest)} update(s)")
        for m in rest[:20]:
            print(f"  {one_line(m, 400)}")
    return 0


def maintain_all(vault: Path) -> list[str]:
    total: list[str] = []
    names = VaultNames.scan(vault)
    for ws in find_workspaces(vault):
        try:
            msgs = maintain(ws, names, vault)
        except Exception as exc:                       # noqa: BLE001 - fail open
            print(f"vault-maintain: {ws.name}: {exc}", file=sys.stderr)
            continue
        total += [f"{ws.name}: {m}" for m in msgs]
    return total


if __name__ == "__main__":
    sys.exit(main())

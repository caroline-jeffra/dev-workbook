# Optional integrations

Two tools make some skills better when they are there: **graphify** (a knowledge graph of a repo) and the **Excalidraw** Obsidian plugin (editable drawings). **Neither is required.** Every skill works the same without them.

## Ground rules

- **Detect, never require.** Check the way the table below says. Absent → do exactly what the skill does anyway, and don't mention the tool.
- **Never install, enable or build.** A graph costs minutes and, for docs, many tokens; only the user starts one. The single exception is an **offer**: ingest-project-docs may suggest `/graphify` once for a newly ingested repo with no graph, when graphify is installed.
- **Distil, don't copy.** What reaches the vault is a few curated lines with a link to the source. Never write graph output into the vault: no `graphify export obsidian`, no `--obsidian`, no `export wiki`, no `graph.json` or `graph.html` copies. Thousands of generated notes would break the naming lint and swamp the vault's graph view.

## Detecting them

| Tool | Present when | Check |
| --- | --- | --- |
| graphify graph | the repo holds a built graph | `[ -f graphify-out/graph.json ]` from the repo root |
| graphify CLI | installed, with or without a graph | `command -v graphify` |
| Excalidraw | the vault has the plugin, or holds drawings | `[ -d "$DEVWB_VAULT/.obsidian/plugins/obsidian-excalidraw-plugin" ]`, or any `*.excalidraw.md` in the vault |

## graphify

**What a graph holds:**

- `graphify-out/GRAPH_REPORT.md` — community hubs (the repo's areas), god nodes (its most connected abstractions), surprising connections and import cycles.
- `graphify-out/graph.json` — every node with its `source_file`, `community` and `community_name`, plus `built_at_commit`.
- The CLI, run from the repo root: `graphify query "<question>"`, `graphify path "A" "B"`, `graphify explain "X"`, `graphify god-nodes`.

**Check it's fresh before trusting it.** A graph is a snapshot:

```bash
built=$(python3 -c "import json;print(json.load(open('graphify-out/graph.json')).get('built_at_commit',''))")
[ -n "$built" ] && git rev-list --count "$built"..HEAD
```

More than ~50 commits behind, or an unknown commit → treat the graph as a map, not the truth, and say so ("graph is 120 commits behind"). Mention `graphify update .` (code only, no model calls) in one line; don't run it.

**Skip the noise.** Large repos put vendored code in their own communities: type definitions, `vendor/`, `node_modules/`, test mocks of third-party clients, copied-in plugins. Judge a community by its files, not its label, and leave out any whose files the team didn't write.

**Where each skill uses it:**

| Skill | Use |
| --- | --- |
| ingest-project-docs | Seed `Research/ArchitectureMap.md` from the report: one bullet per real area (5–12), its key files and god nodes, and a link to `graphify-out/graph.html` by repo path. The area names become the vocabulary for area-first note names and candidate topics in `.vault-config.json`. |
| manage-project-workspaces | While working, answer "where does X live", "what calls Y" and "how do A and B connect" with `graphify query` / `path` before a text search. The answer goes into a note only if it's worth keeping, as a sentence, not a dump. |
| summarize-contribution | Map the user's changed files onto communities to show the breadth of what they owned (see below). |

**Ownership by area** (summarize-contribution). Count the files the user *modified* in each community; added files are left out, because an import of vendored code would swamp everything else:

```bash
git log --author="$ME" --basic-regexp --no-merges --diff-filter=M --name-only --format= \
  | grep -vE '(^|/)(vendor|node_modules|dist|build)/|\.min\.|\.d\.ts$|\.lock$' | sort -u > /tmp/mine.txt
python3 - graphify-out/graph.json /tmp/mine.txt <<'EOF'
import collections, json, sys
g = json.load(open(sys.argv[1]))
mine = set(open(sys.argv[2]).read().splitlines())
files = collections.defaultdict(set)
for n in g["nodes"]:
    if n.get("source_file") and n.get("community_name"):
        files[n["community_name"]].add(n["source_file"])
touched = sorted(((len(fs & mine), len(fs), c) for c, fs in files.items() if fs & mine), reverse=True)
for k, total, c in touched[:15]:
    print(f"{k:>4}/{total:<4} {c}")
print(f"{len(touched)} of {len(files)} communities touched")
EOF
```

Read the top of the list, drop vendored communities, and use the rest as evidence: "changed most of the Inertia controllers and the migration layer". It supports the `cross-team`, `legacy-migration` and `fast-ramp-up` case-study prompts.

## Excalidraw and diagrams

**Every diagram lives in the workspace's `Diagrams/` folder**, named `<Area><Subject>` like any other note (`CheckoutFlow`, `SystemContext`). Notes embed or link the diagram; they don't each own a copy. A small sketch that only makes sense inside one note may stay inline there as a Mermaid block.

**A diagram is one of two forms:**

| Form | When | File |
| --- | --- | --- |
| **Mermaid note** (default) | Always available; renders in Obsidian and on GitHub with no plugin | `Diagrams/<Name>.md`, `type: diagram` — template in [templates/diagram.md](templates/diagram.md) |
| **Excalidraw drawing** | Excalidraw is present **and** the user wants a drawing they can edit by hand | `Diagrams/<Name>.excalidraw.md`, embedded with `![[<Name>.excalidraw]]` |

**Reading a drawing.** In an `.excalidraw.md` file, read the `## Text Elements` section: every label in the drawing, one per paragraph, each ending in a ` ^blockid` to ignore. That is enough to pull component names and arrow labels out of a system diagram. Ignore the `## Drawing` block; the plugin usually stores it compressed. A raw `.excalidraw` file found in a repo is plain JSON:

```bash
jq -r '.elements[] | select(.type == "text" and (.isDeleted | not)) | .text' diagram.excalidraw
```

**Writing a drawing.** The plugin accepts an uncompressed scene and re-saves it in its own format the first time it opens the file:

````markdown
---

excalidraw-plugin: parsed
tags: [excalidraw]

---
==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠==


# Excalidraw Data

## Text Elements
Api gateway ^t1

Queue worker ^t2

%%
## Drawing
```json
{"type": "excalidraw", "version": 2, "source": "dev-workbook", "elements": [
  {"id": "b1", "type": "rectangle", "x": 0, "y": 0, "width": 180, "height": 70, "boundElements": [{"type": "text", "id": "t1"}, {"type": "arrow", "id": "a1"}]},
  {"id": "t1", "type": "text", "x": 10, "y": 25, "width": 160, "height": 20, "text": "Api gateway", "originalText": "Api gateway", "fontSize": 16, "textAlign": "center", "verticalAlign": "middle", "containerId": "b1"},
  {"id": "b2", "type": "rectangle", "x": 300, "y": 0, "width": 180, "height": 70, "boundElements": [{"type": "text", "id": "t2"}, {"type": "arrow", "id": "a1"}]},
  {"id": "t2", "type": "text", "x": 310, "y": 25, "width": 160, "height": 20, "text": "Queue worker", "originalText": "Queue worker", "fontSize": 16, "textAlign": "center", "verticalAlign": "middle", "containerId": "b2"},
  {"id": "a1", "type": "arrow", "x": 180, "y": 35, "width": 120, "height": 0, "points": [[0, 0], [120, 0]], "startBinding": {"elementId": "b1", "focus": 0, "gap": 1}, "endBinding": {"elementId": "b2", "focus": 0, "gap": 1}}
], "appState": {"viewBackgroundColor": "#ffffff"}, "files": {}}
```
%%
````

- Give every element an `id`, `type`, `x`, `y`, `width` and `height`; the plugin fills in the rest when it loads the scene.
- Bind a label to its box both ways (`containerId` on the text, a `boundElements` entry on the box), and an arrow to its ends with `startBinding` / `endBinding`, so the drawing stays connected when the user drags things.
- List every label under `## Text Elements` with the text element's id as its block id, so other notes and skills can read the drawing without opening it.
- Lay boxes on a grid (~300 px apart) left to right in the direction of flow. The user tidies by hand; the job is a correct, connected first draft.
- **Never edit an existing drawing's `## Drawing` block.** To change a drawing the user has worked on, describe the change and let them make it, or write a new drawing beside it.

**The maintainer leaves drawings alone.** The session-end hook never rewrites a drawing's frontmatter or body, and the lint checks only its name and that it sits in `Diagrams/`. A drawing made in Obsidian lands in the plugin's own folder (`Excalidraw/`, named `Drawing <date>`) and shows up in the lint as `bad-name`; move it into the workspace's `Diagrams/` and give it a name.

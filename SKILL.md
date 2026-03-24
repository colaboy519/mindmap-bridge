---
name: mindmap
description: |
  Use when the user specifically asks for an "obsidian mindmap" or a mindmap saved
  to Obsidian vault. Do NOT activate for general mindmap requests (e.g. markdown-only
  or Mermaid mindmaps). Also use when syncing Obsidian canvas edits back to markdown,
  or expanding an existing Obsidian mindmap.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
  - WebSearch
  - WebFetch
  - AskUserQuestion
---

# /mindmap — Obsidian Visual Knowledge Maps

## Overview

Dual-format knowledge maps: agents edit **markdown**, humans edit **Obsidian Canvas** visually.
A bridge tool converts between them. Supports both hierarchical trees and arbitrary graphs.

## Key Paths

| What | Path |
|------|------|
| Bridge CLI | `~/dev/tools/mindmap-bridge/mindmap_bridge.py` |
| Python API | `~/dev/tools/mindmap-bridge/mindmap_api.py` |
| Obsidian vault | `~/shared/vault` |
| Default save location | `~/shared/vault/Knowledge/<topic-slug>` |

## Step 1: Choose the Right Format

Before writing anything, think about the knowledge structure:

| Structure | Format | When to use |
|-----------|--------|-------------|
| Hierarchy / taxonomy | **Tree** | Topics with clear parent-child: "ML algorithms", "programming languages" |
| Architecture / systems | **Graph with zones** | Components with cross-cutting dependencies, layered systems |
| Processes / flows | **Graph with labeled edges** | Request flows, data pipelines, state machines |
| Concept relationships | **Free-form graph** | Ideas with many-to-many relationships, no clear hierarchy |

If the topic has any of these, a tree is the wrong format:
- Shared dependencies (N nodes depend on the same thing)
- Bidirectional relationships
- Cross-cutting concerns that touch many branches
- Cycles or feedback loops

When in doubt, start with a tree and add cross-links if needed. The bridge auto-detects format.

## Status Markers

Every node gets a status marker indicating exploration depth.

| Marker | Meaning | Canvas Color |
|--------|---------|----------|
| ★ | Root / key insight | Purple (6) |
| ✦ | Explored in depth | Green (4) |
| ⬡ | Partially explored | Cyan (5) |
| ○ | Stub (needs expansion) | Default grey (0) |
| ⚡ | Active / in-progress | Red (1) |

## Format A: Tree (Hierarchical)

```markdown
# Topic Title

- Branch One ⬡
  - Child Node ✦ — brief explanation
    - Sub-child ○
    - Why? ★ — non-obvious reasoning
  - Another Child ○
- Branch Two ○
```

Rules: 2-space indent, `- ` prefix, status marker after text, optional explanation after ` — `.

## Format B: Graph (Nodes + Edges)

```markdown
# System Name
<!-- format: graph -->

## Zones
- Client Layer
- Backend
- Infrastructure

## Nodes
- API Gateway ✦ [Client Layer] — routes inbound traffic
- Order Service ⬡ [Backend] — orchestrates checkout
- Kafka ✦ [Infrastructure] — event backbone

## Edges
- API Gateway -> Order Service | sync HTTP
- Order Service -> Kafka | publishes events
- Kafka -> Notification Service | subscribes
- Order Service <-> Inventory Service | sync + events
```

Rules:
- `<!-- format: graph -->` tells the bridge to use graph parser
- Zones are optional — if present, nodes are laid out in zone columns
- `[Zone Name]` after node name assigns it to a zone
- `->` directed edge, `<->` bidirectional, `-->` dashed/weak
- `| label` after edge is optional relationship label

## Shared Rules (Both Formats)

- Add `Why?` / `How?` nodes where reasoning is non-obvious — these are what humans remember
- Only mark ✦ if you could explain it confidently; use ⬡ if uncertain
- Micro-explanations after ` — ` should surprise — skip if obvious from the name

## Subcommands

### `/mindmap create <topic>`

1. **Think about the structure first.** What format fits this topic? (see Step 1)
2. Research the topic (web search if needed)
3. Write the markdown in the chosen format
4. Save and convert:

```bash
VAULT="$HOME/shared/vault"
TOPIC="<topic-slug>"
cd ~/dev/tools/mindmap-bridge
python3 mindmap_bridge.py to-canvas "$VAULT/Knowledge/$TOPIC.md" "$VAULT/Knowledge/$TOPIC.canvas"
```

### `/mindmap expand <vault-path>`

```python
import sys; sys.path.insert(0, str(Path.home() / "dev/tools/mindmap-bridge"))
from mindmap_api import MindmapBuilder
mm = MindmapBuilder.load_from_vault("<vault-path-without-extension>")
print("Stubs:", mm.find_stubs())
```

For graph-format files, read the markdown directly, add nodes/edges, re-run bridge.

### `/mindmap sync <vault-path>`

```bash
cd ~/dev/tools/mindmap-bridge
python3 mindmap_bridge.py to-markdown "$HOME/shared/vault/<path>.canvas" "$HOME/shared/vault/<path>.md"
```

### `/mindmap status <vault-path>` and `/mindmap list`

Report node counts, status breakdown, stubs to expand. List all `.canvas` files in vault.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Always using tree format | Think about structure first — architecture and flows need graphs |
| Writing canvas JSON directly | Write markdown, use the bridge to convert |
| Forgetting status markers | Every node needs ✦/⬡/○ — the core learning feature |
| Using colors for categories | Colors encode exploration depth, not topic categories |
| Skipping "Why?" nodes | Most valuable nodes for learning — add for non-obvious concepts |
| Forcing a tree on a graph topic | If you see shared dependencies or cross-cutting concerns, use graph format |

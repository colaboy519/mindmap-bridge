---
name: mindmap
description: |
  Use when asked to create, expand, or manage a mindmap, knowledge map, or visual
  topic exploration in Obsidian. Also use when syncing visual canvas edits back to
  a structured format, or when asked to "map out" a topic for learning.
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

# /mindmap — Obsidian Mindmaps for AI + Human Collaboration

## Overview

Dual-format mindmaps: agents edit **markdown**, humans edit **Obsidian Canvas** visually.
A bridge tool converts between them bidirectionally.

## Key Paths

| What | Path |
|------|------|
| Bridge CLI | `~/dev/tools/mindmap-bridge/mindmap_bridge.py` |
| Python API | `~/dev/tools/mindmap-bridge/mindmap_api.py` |
| Obsidian vault | `~/shared/vault` |
| Default save location | `~/shared/vault/Knowledge/<topic-slug>` |

## Status Markers

Every node gets a status marker indicating exploration depth. This is the core
learning feature — humans can see what's well-understood vs. what's a stub.

| Marker | Meaning | Canvas Color |
|--------|---------|----------|
| ★ | Root / key insight | Purple (6) |
| ✦ | Explored in depth | Green (4) |
| ⬡ | Partially explored | Cyan (5) |
| ○ | Stub (needs expansion) | Default grey (0) |
| ⚡ | Active / in-progress | Red (1) |

## Markdown Format

```markdown
# Topic Title

- Branch One ⬡
  - Child Node ✦ — brief explanation of what this is
    - Sub-child ○
    - Why? ★ — the non-obvious reason this matters
  - Another Child ○
- Branch Two ○
```

Rules:
- 2-space indentation per level
- `- ` prefix for all nodes
- Status marker after the node text
- Optional micro-explanation after ` — ` (em dash)
- Add `Why?` / `How?` nodes where reasoning is non-obvious — these are what humans remember
- Only mark ✦ if you could explain it to someone; use ⬡ if uncertain

## Subcommands

Parse `$ARGUMENTS` to determine the subcommand.

### `/mindmap create <topic>`

1. Research the topic (web search if needed for breadth)
2. Build markdown with 3-5 top-level branches, each with 2-4 children
3. Mark nodes with honest status: ✦ explored, ⬡ partial, ○ stubs
4. Add micro-explanations and "Why?" nodes for key concepts
5. Save to vault:

```bash
VAULT="$HOME/shared/vault"
TOPIC="<topic-slug>"
# Write the markdown source
# Then convert:
cd ~/dev/tools/mindmap-bridge
python3 mindmap_bridge.py to-canvas "$VAULT/Knowledge/$TOPIC.md" "$VAULT/Knowledge/$TOPIC.canvas"
```

Ask user where to save if unclear. Default: `Knowledge/<topic-slug>`.

### `/mindmap expand <vault-path>`

1. Load existing mindmap via Python API:

```python
import sys; sys.path.insert(0, str(Path.home() / "dev/tools/mindmap-bridge"))
from mindmap_api import MindmapBuilder
mm = MindmapBuilder.load_from_vault("<vault-path-without-extension>")
print("Stubs:", mm.find_stubs())
print("Partial:", mm.find_partial())
```

2. Show user what's unexplored, ask which to expand (or expand all)
3. Research and add children, update parent status ○→⬡ or ⬡→✦
4. Save: `mm.save_to_vault("<vault-path>")`

### `/mindmap sync <vault-path>`

Reconcile human visual edits with markdown source:

```bash
cd ~/dev/tools/mindmap-bridge
# Human edited canvas → update markdown:
python3 mindmap_bridge.py to-markdown "$HOME/shared/vault/<path>.canvas" "$HOME/shared/vault/<path>.md"
# Or agent edited markdown → update canvas:
python3 mindmap_bridge.py to-canvas "$HOME/shared/vault/<path>.md" "$HOME/shared/vault/<path>.canvas"
```

### `/mindmap status <vault-path>`

Load mindmap and report: total nodes, breakdown by status, list of stubs, suggest next areas.

### `/mindmap list`

Find all mindmap canvas files in vault and show each with node count.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Writing canvas JSON directly | Always write markdown first, then use bridge to convert |
| Forgetting status markers | Every node needs ✦/⬡/○ — this is the core learning feature |
| Using colors for categories | Colors encode exploration depth (status), not topic categories |
| Skipping "Why?" nodes | These are the most valuable nodes for learning — add them for non-obvious concepts |
| Not loading canvas on expand | Always `load_from_vault` (prefers canvas) to preserve human visual edits |

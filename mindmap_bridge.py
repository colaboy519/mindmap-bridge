#!/usr/bin/env python3
"""
Mindmap Bridge: bidirectional conversion between indented markdown and Obsidian Canvas.

Agent writes markdown → bridge creates .canvas → human edits visually → bridge reads back to markdown.

Usage:
    # Markdown → Canvas
    python mindmap_bridge.py to-canvas input.md output.canvas

    # Canvas → Markdown
    python mindmap_bridge.py to-markdown input.canvas output.md

    # Watch mode: auto-sync markdown ↔ canvas on file change
    python mindmap_bridge.py watch file.md file.canvas
"""

import json
import sys
import re
import uuid
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ── Node status markers ──────────────────────────────────────────────────────

STATUS_MARKERS = {
    "✦": {"label": "explored", "color": "4"},     # green
    "⬡": {"label": "partial", "color": "5"},      # purple
    "○": {"label": "stub", "color": "0"},          # default/grey
    "★": {"label": "key_insight", "color": "6"},   # yellow
    "⚡": {"label": "active", "color": "1"},        # red
}

# Canvas color palette (Obsidian's built-in):
# 0=default, 1=red, 2=orange, 3=yellow, 4=green, 5=cyan, 6=purple


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class MindmapNode:
    text: str
    status: str = "○"
    explanation: str = ""
    children: list = field(default_factory=list)
    id: str = ""
    # Layout fields (computed)
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0

    def __post_init__(self):
        if not self.id:
            self.id = _stable_id(self.text)

    @property
    def display_text(self) -> str:
        """Full display text for the node."""
        parts = [self.text]
        if self.explanation:
            parts.append(f"— {self.explanation}")
        return " ".join(parts)

    @property
    def subtree_size(self) -> int:
        """Total number of leaf-equivalent nodes in this subtree."""
        if not self.children:
            return 1
        return sum(c.subtree_size for c in self.children)


def _stable_id(text: str) -> str:
    """Generate a deterministic short ID from text so canvas node IDs are stable across regenerations."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


# ── Markdown parser ──────────────────────────────────────────────────────────

def parse_markdown(text: str) -> MindmapNode:
    """Parse indented markdown list into a tree of MindmapNodes."""
    lines = text.strip().split("\n")
    root = None
    stack: list[tuple[int, MindmapNode]] = []  # (indent_level, node)

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Title line (# heading) becomes root
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            root = MindmapNode(text=title, status="★")
            stack = [(-1, root)]
            continue

        # Skip HTML comments (agent metadata)
        if stripped.startswith("<!--") or stripped.startswith("-->"):
            continue

        # Calculate indent level
        indent = len(line) - len(line.lstrip())
        # Normalize: treat 2-space and 4-space indents, plus "- " prefix
        stripped = stripped.lstrip("- ").strip()

        # Extract status marker
        status = "○"
        for marker in STATUS_MARKERS:
            if marker in stripped:
                status = marker
                stripped = stripped.replace(marker, "").strip()
                break

        # Extract explanation after " — " or " - " dash
        explanation = ""
        for sep in [" — ", " — ", " – "]:
            if sep in stripped:
                parts = stripped.split(sep, 1)
                stripped = parts[0].strip()
                explanation = parts[1].strip()
                break

        node = MindmapNode(text=stripped, status=status, explanation=explanation)

        # Find parent: walk back the stack to find the last node with a smaller indent
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        parent = stack[-1][1]
        parent.children.append(node)
        stack.append((indent, node))

    if root is None:
        root = MindmapNode(text="Mindmap", status="★")

    return root


# ── Tree layout engine ───────────────────────────────────────────────────────

# Layout constants
NODE_BASE_WIDTH = 250
NODE_HEIGHT = 60
NODE_CHAR_WIDTH = 8        # approx pixels per character for width calc
NODE_MIN_WIDTH = 160
NODE_MAX_WIDTH = 400
H_GAP = 80                 # horizontal gap between depth levels
V_GAP = 20                 # vertical gap between sibling nodes
ROOT_X = 50
ROOT_Y = 50


def _compute_node_size(node: MindmapNode) -> tuple[float, float]:
    """Compute width and height based on text length."""
    text = node.display_text
    char_width = len(text) * NODE_CHAR_WIDTH
    width = max(NODE_MIN_WIDTH, min(NODE_MAX_WIDTH, char_width + 40))
    # Multi-line: if text is longer than max_width, increase height
    lines = max(1, char_width // NODE_MAX_WIDTH + 1)
    height = NODE_HEIGHT + (lines - 1) * 24
    return width, height


def layout_tree(root: MindmapNode, x: float = ROOT_X, y: float = ROOT_Y) -> float:
    """
    Lay out the tree left-to-right. Returns total height used.

    Algorithm: each node's y-center is the center of its children's vertical span.
    Leaf nodes are stacked vertically with V_GAP spacing.
    """
    root.width, root.height = _compute_node_size(root)
    root.x = x

    if not root.children:
        root.y = y
        return root.height

    # Recursively layout children
    child_x = x + root.width + H_GAP
    current_y = y
    total_height = 0

    for i, child in enumerate(root.children):
        child_height = layout_tree(child, child_x, current_y)
        current_y += child_height + V_GAP
        total_height += child_height + (V_GAP if i < len(root.children) - 1 else 0)

    # Center this node vertically relative to its children
    first_child_center = root.children[0].y + root.children[0].height / 2
    last_child_center = root.children[-1].y + root.children[-1].height / 2
    root.y = (first_child_center + last_child_center) / 2 - root.height / 2

    return total_height


# ── Canvas generator ─────────────────────────────────────────────────────────

def tree_to_canvas(root: MindmapNode) -> dict:
    """Convert a laid-out tree into Obsidian Canvas JSON format."""
    nodes = []
    edges = []

    def _walk(node: MindmapNode):
        # Determine color from status
        color = STATUS_MARKERS.get(node.status, {}).get("color", "0")

        canvas_node = {
            "id": node.id,
            "type": "text",
            "text": node.display_text,
            "x": int(node.x),
            "y": int(node.y),
            "width": int(node.width),
            "height": int(node.height),
        }
        if color != "0":
            canvas_node["color"] = color

        nodes.append(canvas_node)

        for child in node.children:
            edges.append({
                "id": _stable_id(f"{node.id}->{child.id}"),
                "fromNode": node.id,
                "fromSide": "right",
                "toNode": child.id,
                "toSide": "left",
            })
            _walk(child)

    _walk(root)
    return {"nodes": nodes, "edges": edges}


# ── Canvas parser (reverse direction) ────────────────────────────────────────

def canvas_to_tree(canvas: dict) -> MindmapNode:
    """Parse Obsidian Canvas JSON back into a MindmapNode tree."""
    nodes_by_id = {}
    children_map: dict[str, list[str]] = {}
    child_ids = set()

    # Build node lookup
    for n in canvas.get("nodes", []):
        if n.get("type") != "text":
            continue
        text = n.get("text", "").strip()
        color = str(n.get("color", "0"))

        # Reverse-map color to status
        status = "○"
        for marker, info in STATUS_MARKERS.items():
            if info["color"] == color:
                status = marker
                break

        # Parse "text — explanation" back out
        explanation = ""
        for sep in [" — ", " — ", " – "]:
            if sep in text:
                parts = text.split(sep, 1)
                text = parts[0].strip()
                explanation = parts[1].strip()
                break

        node = MindmapNode(text=text, status=status, explanation=explanation, id=n["id"])
        node.x = n.get("x", 0)
        node.y = n.get("y", 0)
        nodes_by_id[n["id"]] = node

    # Build parent→children from edges
    for e in canvas.get("edges", []):
        from_id = e.get("fromNode")
        to_id = e.get("toNode")
        if from_id and to_id:
            children_map.setdefault(from_id, []).append(to_id)
            child_ids.add(to_id)

    # Root = node that is never a child
    root_candidates = [nid for nid in nodes_by_id if nid not in child_ids]
    if not root_candidates:
        return MindmapNode(text="Empty", status="○")

    # Pick the leftmost node as root
    root_id = min(root_candidates, key=lambda nid: nodes_by_id[nid].x)
    root = nodes_by_id[root_id]

    # Recursively attach children (sorted by y-position for consistent ordering)
    def _attach(node: MindmapNode):
        child_ids_list = children_map.get(node.id, [])
        child_nodes = [nodes_by_id[cid] for cid in child_ids_list if cid in nodes_by_id]
        child_nodes.sort(key=lambda n: n.y)
        node.children = child_nodes
        for child in node.children:
            _attach(child)

    _attach(root)
    return root


# ── Markdown generator (reverse direction) ───────────────────────────────────

def tree_to_markdown(root: MindmapNode) -> str:
    """Convert a MindmapNode tree back to indented markdown."""
    lines = [f"# {root.text}\n"]

    def _walk(node: MindmapNode, depth: int):
        indent = "  " * depth
        status_str = f" {node.status}" if node.status != "○" else ""
        expl_str = f" — {node.explanation}" if node.explanation else ""
        lines.append(f"{indent}- {node.text}{status_str}{expl_str}")
        for child in node.children:
            _walk(child, depth + 1)

    for child in root.children:
        _walk(child, 0)

    return "\n".join(lines) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────────

def cmd_to_canvas(md_path: str, canvas_path: str):
    """Convert markdown mindmap to Obsidian Canvas."""
    md_text = Path(md_path).read_text(encoding="utf-8")
    root = parse_markdown(md_text)
    layout_tree(root)
    canvas = tree_to_canvas(root)
    Path(canvas_path).write_text(json.dumps(canvas, indent=2, ensure_ascii=False), encoding="utf-8")
    node_count = len(canvas["nodes"])
    print(f"✓ Created canvas with {node_count} nodes → {canvas_path}")


def cmd_to_markdown(canvas_path: str, md_path: str):
    """Convert Obsidian Canvas back to markdown mindmap."""
    canvas = json.loads(Path(canvas_path).read_text(encoding="utf-8"))
    root = canvas_to_tree(canvas)
    md_text = tree_to_markdown(root)
    Path(md_path).write_text(md_text, encoding="utf-8")
    print(f"✓ Exported markdown → {md_path}")


def cmd_watch(md_path: str, canvas_path: str):
    """Watch both files and sync changes bidirectionally."""
    import time

    md_p = Path(md_path)
    canvas_p = Path(canvas_path)

    # Initial sync: md → canvas if canvas doesn't exist or is empty
    if not canvas_p.exists() or canvas_p.stat().st_size <= 2:
        if md_p.exists():
            cmd_to_canvas(md_path, canvas_path)

    md_mtime = md_p.stat().st_mtime if md_p.exists() else 0
    canvas_mtime = canvas_p.stat().st_mtime if canvas_p.exists() else 0

    print(f"Watching for changes... (Ctrl+C to stop)")
    print(f"  Markdown: {md_path}")
    print(f"  Canvas:   {canvas_path}")

    try:
        while True:
            time.sleep(1)
            new_md_mtime = md_p.stat().st_mtime if md_p.exists() else 0
            new_canvas_mtime = canvas_p.stat().st_mtime if canvas_p.exists() else 0

            if new_md_mtime > md_mtime and new_md_mtime > new_canvas_mtime:
                print(f"  → Markdown changed, updating canvas...")
                cmd_to_canvas(md_path, canvas_path)
                md_mtime = new_md_mtime
                canvas_mtime = Path(canvas_path).stat().st_mtime

            elif new_canvas_mtime > canvas_mtime and new_canvas_mtime > new_md_mtime:
                print(f"  ← Canvas changed, updating markdown...")
                cmd_to_markdown(canvas_path, md_path)
                canvas_mtime = new_canvas_mtime
                md_mtime = Path(md_path).stat().st_mtime
            else:
                md_mtime = new_md_mtime
                canvas_mtime = new_canvas_mtime

    except KeyboardInterrupt:
        print("\nStopped watching.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "to-canvas" and len(sys.argv) == 4:
        cmd_to_canvas(sys.argv[2], sys.argv[3])
    elif cmd == "to-markdown" and len(sys.argv) == 4:
        cmd_to_markdown(sys.argv[2], sys.argv[3])
    elif cmd == "watch" and len(sys.argv) == 4:
        cmd_watch(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

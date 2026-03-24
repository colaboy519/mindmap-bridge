"""
Mindmap API: programmatic interface for AI agents to build and iterate on mindmaps.

Usage by agents:
    from mindmap_api import MindmapBuilder

    mm = MindmapBuilder("Transformer Architecture")
    attn = mm.add("Attention Mechanism", status="⬡")
    sa = mm.add("Self-Attention", parent=attn, status="✦", explain="each token attends to all others")
    mm.add("Query, Key, Value", parent=sa, status="✦", explain="three learned projections")

    mm.save_to_vault("Knowledge/transformer-architecture")  # saves both .md and .canvas

    # Later, load human edits back:
    mm2 = MindmapBuilder.load_from_vault("Knowledge/transformer-architecture")
    mm2.add("New Discovery", parent="Self-Attention", status="⬡", explain="just found this")
    mm2.save_to_vault("Knowledge/transformer-architecture")
"""

import json
from pathlib import Path
from typing import Optional, Union
from mindmap_bridge import (
    MindmapNode, parse_markdown, layout_tree, tree_to_canvas,
    canvas_to_tree, tree_to_markdown
)


VAULT_PATH = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian_vault"


class MindmapBuilder:
    """Fluent API for agents to build and modify mindmaps."""

    def __init__(self, title: str = "Mindmap"):
        self.root = MindmapNode(text=title, status="★")
        self._index: dict[str, MindmapNode] = {title: self.root}

    def add(
        self,
        text: str,
        parent: Optional[Union[str, MindmapNode]] = None,
        status: str = "○",
        explain: str = "",
    ) -> MindmapNode:
        """Add a node. Parent can be a node object or text string to find by name."""
        if parent is None:
            parent_node = self.root
        elif isinstance(parent, str):
            parent_node = self._find(parent)
            if parent_node is None:
                raise ValueError(f"Parent node '{parent}' not found")
        else:
            parent_node = parent

        node = MindmapNode(text=text, status=status, explanation=explain)
        parent_node.children.append(node)
        self._index[text] = node
        return node

    def update(self, text: str, status: Optional[str] = None, explain: Optional[str] = None):
        """Update an existing node's status or explanation."""
        node = self._find(text)
        if node is None:
            raise ValueError(f"Node '{text}' not found")
        if status is not None:
            node.status = status
        if explain is not None:
            node.explanation = explain

    def remove(self, text: str) -> bool:
        """Remove a node and its subtree. Returns True if found and removed."""
        def _remove_from(parent: MindmapNode) -> bool:
            for i, child in enumerate(parent.children):
                if child.text == text:
                    parent.children.pop(i)
                    return True
                if _remove_from(child):
                    return True
            return False
        return _remove_from(self.root)

    def move(self, text: str, new_parent: str):
        """Move a node (and its subtree) under a different parent."""
        node = self._find(text)
        if node is None:
            raise ValueError(f"Node '{text}' not found")
        self.remove(text)
        parent = self._find(new_parent)
        if parent is None:
            raise ValueError(f"New parent '{new_parent}' not found")
        parent.children.append(node)

    def find_stubs(self) -> list[str]:
        """Find all ○ stub nodes that need expanding."""
        stubs = []
        def _walk(node):
            if node.status == "○" and node != self.root:
                stubs.append(node.text)
            for child in node.children:
                _walk(child)
        _walk(self.root)
        return stubs

    def find_partial(self) -> list[str]:
        """Find all ⬡ partially-explored nodes."""
        partial = []
        def _walk(node):
            if node.status == "⬡":
                partial.append(node.text)
            for child in node.children:
                _walk(child)
        _walk(self.root)
        return partial

    def stats(self) -> dict:
        """Get a summary of the mindmap's exploration state."""
        counts = {"✦": 0, "⬡": 0, "○": 0, "★": 0, "⚡": 0, "total": 0}
        def _walk(node):
            counts["total"] += 1
            counts[node.status] = counts.get(node.status, 0) + 1
            for child in node.children:
                _walk(child)
        _walk(self.root)
        return counts

    # ── Persistence ──────────────────────────────────────────────────────

    def to_markdown(self) -> str:
        return tree_to_markdown(self.root)

    def to_canvas_json(self) -> dict:
        layout_tree(self.root)
        return tree_to_canvas(self.root)

    def save_to_vault(self, relative_path: str):
        """Save both .md and .canvas to the Obsidian vault."""
        base = VAULT_PATH / relative_path
        md_path = base.with_suffix(".md")
        canvas_path = base.with_suffix(".canvas")

        md_path.parent.mkdir(parents=True, exist_ok=True)

        md_path.write_text(self.to_markdown(), encoding="utf-8")
        canvas_json = self.to_canvas_json()
        canvas_path.write_text(
            json.dumps(canvas_json, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        stats = self.stats()
        print(f"✓ Saved to vault: {relative_path}")
        print(f"  Nodes: {stats['total']} (✦ {stats['✦']} explored, ⬡ {stats['⬡']} partial, ○ {stats['○']} stubs)")

    @classmethod
    def load_from_vault(cls, relative_path: str) -> "MindmapBuilder":
        """Load from the Obsidian vault. Prefers canvas (preserves human edits) over markdown."""
        base = VAULT_PATH / relative_path
        canvas_path = base.with_suffix(".canvas")
        md_path = base.with_suffix(".md")

        if canvas_path.exists() and canvas_path.stat().st_size > 2:
            canvas = json.loads(canvas_path.read_text(encoding="utf-8"))
            root = canvas_to_tree(canvas)
        elif md_path.exists():
            md_text = md_path.read_text(encoding="utf-8")
            root = parse_markdown(md_text)
        else:
            raise FileNotFoundError(f"No mindmap found at {base}")

        builder = cls.__new__(cls)
        builder.root = root
        builder._index = {}
        builder._rebuild_index(root)
        return builder

    @classmethod
    def load_from_markdown(cls, text: str) -> "MindmapBuilder":
        """Load from a markdown string."""
        root = parse_markdown(text)
        builder = cls.__new__(cls)
        builder.root = root
        builder._index = {}
        builder._rebuild_index(root)
        return builder

    # ── Internal ─────────────────────────────────────────────────────────

    def _find(self, text: str) -> Optional[MindmapNode]:
        if text in self._index:
            return self._index[text]
        # Fallback: walk the tree
        def _walk(node):
            if node.text == text:
                self._index[text] = node
                return node
            for child in node.children:
                result = _walk(child)
                if result:
                    return result
            return None
        return _walk(self.root)

    def _rebuild_index(self, node: MindmapNode):
        self._index[node.text] = node
        for child in node.children:
            self._rebuild_index(child)

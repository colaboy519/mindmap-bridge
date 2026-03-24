#!/usr/bin/env python3
"""
Graph Bridge: converts markdown graph definitions to Obsidian Canvas.

Supports arbitrary node+edge graphs with optional zones for spatial grouping.
Complements mindmap_bridge.py (which handles tree/hierarchy format).

Markdown format:
    # Title
    <!-- format: graph -->

    ## Zones (optional)
    - Zone Name

    ## Nodes
    - Node Name ✦ [Zone Name] — description

    ## Edges
    - Source -> Target | label
    - Source <-> Target | bidirectional label
    - Source --> Target | dashed/weak link
"""

import json
import re
import hashlib
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Reuse status markers from the tree bridge
STATUS_MARKERS = {
    "✦": {"label": "explored", "color": "4"},
    "⬡": {"label": "partial", "color": "5"},
    "○": {"label": "stub", "color": "0"},
    "★": {"label": "key_insight", "color": "6"},
    "⚡": {"label": "active", "color": "1"},
}


@dataclass
class GraphNode:
    name: str
    status: str = "○"
    explanation: str = ""
    zone: str = ""
    id: str = ""
    x: float = 0
    y: float = 0
    width: float = 250
    height: float = 60

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(self.name.encode()).hexdigest()[:12]


@dataclass
class GraphEdge:
    source: str
    target: str
    label: str = ""
    bidirectional: bool = False
    dashed: bool = False
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"{self.source}->{self.target}".encode()).hexdigest()[:12]


@dataclass
class Graph:
    title: str = "Graph"
    zones: list = field(default_factory=list)
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)


# ── Markdown parser ──────────────────────────────────────────────────────────

def parse_graph_markdown(text: str) -> Graph:
    """Parse a graph-format markdown file into a Graph."""
    graph = Graph()
    lines = text.strip().split("\n")
    section = None  # "zones", "nodes", "edges"

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue

        # Title
        if stripped.startswith("# "):
            graph.title = stripped[2:].strip()
            continue

        # Section headers
        lower = stripped.lower()
        if stripped.startswith("## "):
            if "zone" in lower:
                section = "zones"
            elif "node" in lower:
                section = "nodes"
            elif "edge" in lower or "link" in lower or "connection" in lower or "relationship" in lower:
                section = "edges"
            else:
                section = "nodes"  # default unknown sections to nodes
            continue

        if not stripped.startswith("- "):
            continue
        content = stripped[2:].strip()

        if section == "zones":
            graph.zones.append(content)

        elif section == "nodes":
            node = _parse_node_line(content)
            graph.nodes.append(node)

        elif section == "edges":
            edge = _parse_edge_line(content)
            if edge:
                graph.edges.append(edge)

    return graph


def _parse_node_line(text: str) -> GraphNode:
    """Parse: 'Node Name ✦ [Zone] — explanation'"""
    zone = ""
    zone_match = re.search(r'\[([^\]]+)\]', text)
    if zone_match:
        zone = zone_match.group(1).strip()
        text = text[:zone_match.start()] + text[zone_match.end():]

    status = "○"
    for marker in STATUS_MARKERS:
        if marker in text:
            status = marker
            text = text.replace(marker, "").strip()
            break

    explanation = ""
    for sep in [" — ", " — ", " – "]:
        if sep in text:
            parts = text.split(sep, 1)
            text = parts[0].strip()
            explanation = parts[1].strip()
            break

    return GraphNode(name=text.strip(), status=status, explanation=explanation, zone=zone)


def _parse_edge_line(text: str) -> Optional[GraphEdge]:
    """Parse: 'Source -> Target | label' or 'Source <-> Target | label'"""
    label = ""
    if "|" in text:
        parts = text.split("|", 1)
        text = parts[0].strip()
        label = parts[1].strip()

    bidirectional = False
    dashed = False

    if "<->" in text:
        parts = text.split("<->", 1)
        bidirectional = True
    elif "-->" in text:
        parts = text.split("-->", 1)
        dashed = True
    elif "->" in text:
        parts = text.split("->", 1)
    else:
        return None

    source = parts[0].strip()
    target = parts[1].strip()
    return GraphEdge(source=source, target=target, label=label,
                     bidirectional=bidirectional, dashed=dashed)


# ── Layout engine ────────────────────────────────────────────────────────────

NODE_WIDTH = 280
NODE_HEIGHT = 60
NODE_CHAR_WIDTH = 7
NODE_MAX_WIDTH = 420
H_GAP = 120
V_GAP = 40
ZONE_PADDING = 60
ZONE_GAP = 100


def _compute_node_size(node: GraphNode) -> tuple[float, float]:
    display = node.name
    if node.explanation:
        display += f" — {node.explanation}"
    char_w = len(display) * NODE_CHAR_WIDTH
    width = max(180, min(NODE_MAX_WIDTH, char_w + 40))
    lines = max(1, char_w // NODE_MAX_WIDTH + 1)
    height = NODE_HEIGHT + (lines - 1) * 24
    return width, height


def layout_graph(graph: Graph):
    """Lay out nodes. If zones exist, arrange in zone columns. Otherwise grid layout."""
    for node in graph.nodes:
        node.width, node.height = _compute_node_size(node)

    if graph.zones:
        _layout_zoned(graph)
    else:
        _layout_grid(graph)


def _layout_zoned(graph: Graph):
    """Arrange nodes in vertical columns per zone, left-to-right."""
    zone_nodes: dict[str, list[GraphNode]] = {z: [] for z in graph.zones}
    unzoned = []

    for node in graph.nodes:
        if node.zone in zone_nodes:
            zone_nodes[node.zone].append(node)
        else:
            unzoned.append(node)

    x = ZONE_PADDING
    for zone_name in graph.zones:
        nodes = zone_nodes[zone_name]
        if not nodes:
            continue

        max_width = max(n.width for n in nodes) if nodes else NODE_WIDTH
        y = ZONE_PADDING
        for node in nodes:
            node.x = x + (max_width - node.width) / 2  # center in column
            node.y = y
            y += node.height + V_GAP

        x += max_width + ZONE_GAP

    # Place unzoned nodes at the end
    if unzoned:
        y = ZONE_PADDING
        for node in unzoned:
            node.x = x
            node.y = y
            y += node.height + V_GAP


def _layout_grid(graph: Graph):
    """Simple grid layout for unzoned graphs."""
    cols = max(1, int(math.sqrt(len(graph.nodes))))
    x, y = ZONE_PADDING, ZONE_PADDING
    max_height_in_row = 0

    for i, node in enumerate(graph.nodes):
        node.x = x
        node.y = y
        max_height_in_row = max(max_height_in_row, node.height)

        if (i + 1) % cols == 0:
            x = ZONE_PADDING
            y += max_height_in_row + V_GAP
            max_height_in_row = 0
        else:
            x += node.width + H_GAP


# ── Canvas generation ─────────────────────────────────────────────────────────

def graph_to_canvas(graph: Graph) -> dict:
    """Convert a laid-out Graph to Obsidian Canvas JSON."""
    canvas_nodes = []
    canvas_edges = []
    node_id_map = {n.name: n.id for n in graph.nodes}

    for node in graph.nodes:
        color = STATUS_MARKERS.get(node.status, {}).get("color", "0")
        display = node.name
        if node.explanation:
            display += f" — {node.explanation}"

        cn = {
            "id": node.id,
            "type": "text",
            "text": display,
            "x": int(node.x),
            "y": int(node.y),
            "width": int(node.width),
            "height": int(node.height),
        }
        if color != "0":
            cn["color"] = color
        canvas_nodes.append(cn)

    for edge in graph.edges:
        from_id = node_id_map.get(edge.source)
        to_id = node_id_map.get(edge.target)
        if not from_id or not to_id:
            continue

        ce = {
            "id": edge.id,
            "fromNode": from_id,
            "fromSide": "right",
            "toNode": to_id,
            "toSide": "left",
        }
        if edge.label:
            ce["label"] = edge.label
        if edge.bidirectional:
            ce["fromEnd"] = "arrow"
            ce["toEnd"] = "arrow"

        canvas_edges.append(ce)

    return {"nodes": canvas_nodes, "edges": canvas_edges}


# ── Canvas parser (reverse) ──────────────────────────────────────────────

def canvas_to_graph(canvas: dict) -> Graph:
    """Parse Obsidian Canvas JSON back to a Graph."""
    graph = Graph()
    id_to_name = {}

    for n in canvas.get("nodes", []):
        if n.get("type") != "text":
            continue
        text = n.get("text", "").strip()
        color = str(n.get("color", "0"))

        status = "○"
        for marker, info in STATUS_MARKERS.items():
            if info["color"] == color:
                status = marker
                break

        explanation = ""
        for sep in [" — ", " — ", " – "]:
            if sep in text:
                parts = text.split(sep, 1)
                text = parts[0].strip()
                explanation = parts[1].strip()
                break

        node = GraphNode(name=text, status=status, explanation=explanation, id=n["id"])
        node.x = n.get("x", 0)
        node.y = n.get("y", 0)
        node.width = n.get("width", 250)
        node.height = n.get("height", 60)
        graph.nodes.append(node)
        id_to_name[n["id"]] = text

    for e in canvas.get("edges", []):
        source = id_to_name.get(e.get("fromNode", ""), "")
        target = id_to_name.get(e.get("toNode", ""), "")
        if source and target:
            bidirectional = e.get("fromEnd") == "arrow" and e.get("toEnd") == "arrow"
            graph.edges.append(GraphEdge(
                source=source, target=target,
                label=e.get("label", ""),
                bidirectional=bidirectional,
                id=e.get("id", "")
            ))

    return graph


# ── Markdown generation (reverse) ────────────────────────────────────────

def graph_to_markdown(graph: Graph) -> str:
    """Convert a Graph back to markdown."""
    lines = [f"# {graph.title}", "<!-- format: graph -->", ""]

    if graph.zones:
        lines.append("## Zones")
        for z in graph.zones:
            lines.append(f"- {z}")
        lines.append("")

    lines.append("## Nodes")
    for node in graph.nodes:
        status_str = f" {node.status}" if node.status != "○" else ""
        zone_str = f" [{node.zone}]" if node.zone else ""
        expl_str = f" — {node.explanation}" if node.explanation else ""
        lines.append(f"- {node.name}{status_str}{zone_str}{expl_str}")
    lines.append("")

    if graph.edges:
        lines.append("## Edges")
        for edge in graph.edges:
            arrow = "<->" if edge.bidirectional else ("-->" if edge.dashed else "->")
            label_str = f" | {edge.label}" if edge.label else ""
            lines.append(f"- {edge.source} {arrow} {edge.target}{label_str}")
        lines.append("")

    return "\n".join(lines) + "\n"


# ── Format detection ─────────────────────────────────────────────────────────

def is_graph_format(text: str) -> bool:
    """Detect if a markdown file uses graph format vs tree format."""
    return "<!-- format: graph -->" in text or "## Nodes" in text or "## Edges" in text

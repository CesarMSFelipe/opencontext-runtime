"""Graph view models for the TUI interactive graph screen."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from opencontext_core.compat import StrEnum

_MAX_NODES = 60


class GraphNodeKind(StrEnum):
    """Kind of node in the graph view."""

    PHASE = "phase"
    FILE = "file"
    SYMBOL = "symbol"
    MEMORY = "memory"
    AGENT = "agent"
    UNKNOWN = "unknown"


class GraphMode(StrEnum):
    """Graph display mode — filters which node types are shown."""

    RUN = "run"
    KG = "kg"
    MEMORY = "memory"
    CONTEXT = "context"
    IMPACT = "impact"


@dataclass
class GraphNodeView:
    """A single node in the rendered graph view."""

    node_id: str
    label: str
    kind: GraphNodeKind = GraphNodeKind.UNKNOWN
    x: float = 0.0
    y: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class GraphEdgeView:
    """A directed edge between two nodes in the graph view."""

    source_id: str
    target_id: str
    label: str = ""
    weight: float = 1.0


@dataclass
class GraphViewState:
    """The rendered state of the graph — capped at _MAX_NODES nodes.

    When the source graph has more than _MAX_NODES nodes, a BFS subgraph
    is selected starting from the focal node.
    """

    nodes: list[GraphNodeView]
    edges: list[GraphEdgeView]
    mode: GraphMode = GraphMode.RUN
    focal_node_id: str | None = None

    @classmethod
    def build(
        cls,
        nodes: list[GraphNodeView],
        edges: list[GraphEdgeView],
        mode: GraphMode = GraphMode.RUN,
        focal_node_id: str | None = None,
    ) -> GraphViewState:
        """Build a GraphViewState, trimming to _MAX_NODES via BFS if needed."""
        if len(nodes) <= _MAX_NODES:
            return cls(nodes=nodes, edges=edges, mode=mode, focal_node_id=focal_node_id)

        # NOTE: BFS subgraph from focal_node (or first node) to cap at _MAX_NODES.
        node_map = {n.node_id: n for n in nodes}
        adjacency: dict[str, list[str]] = {n.node_id: [] for n in nodes}
        for edge in edges:
            if edge.source_id in adjacency:
                adjacency[edge.source_id].append(edge.target_id)
            if edge.target_id in adjacency:
                adjacency[edge.target_id].append(edge.source_id)

        start = focal_node_id if focal_node_id in node_map else nodes[0].node_id
        visited: list[str] = []
        queue: deque[str] = deque([start])
        seen: set[str] = {start}

        while queue and len(visited) < _MAX_NODES:
            current = queue.popleft()
            visited.append(current)
            for neighbor in adjacency.get(current, []):
                if neighbor not in seen and len(visited) + len(queue) < _MAX_NODES:
                    seen.add(neighbor)
                    queue.append(neighbor)

        trimmed_nodes = [node_map[nid] for nid in visited if nid in node_map]
        trimmed_ids = {n.node_id for n in trimmed_nodes}
        trimmed_edges = [
            e for e in edges if e.source_id in trimmed_ids and e.target_id in trimmed_ids
        ]
        return cls(
            nodes=trimmed_nodes,
            edges=trimmed_edges,
            mode=mode,
            focal_node_id=focal_node_id,
        )

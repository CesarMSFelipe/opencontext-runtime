"""LayeredGraphLayout — BFS depth-layer placement for ASCII graph rendering."""

from __future__ import annotations

from collections import deque

from opencontext_cli.tui.graph.models import GraphEdgeView, GraphNodeView


class LayeredGraphLayout:
    """Assigns (x, y) coordinates to nodes using BFS depth layers.

    Layer 0 = root (focal) node at y=0.
    Each subsequent BFS level gets y+1.
    Nodes within a layer are evenly spaced along the x axis.
    """

    def __init__(self, x_spacing: float = 4.0, y_spacing: float = 2.0) -> None:
        self.x_spacing = x_spacing
        self.y_spacing = y_spacing

    def layout(
        self,
        nodes: list[GraphNodeView],
        edges: list[GraphEdgeView],
        focal_id: str | None = None,
    ) -> list[GraphNodeView]:
        """Return *nodes* with updated x/y coordinates. Does not mutate input."""
        if not nodes:
            return []

        node_ids = [n.node_id for n in nodes]
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in edges:
            if edge.source_id in adjacency:
                adjacency[edge.source_id].append(edge.target_id)
            if edge.target_id in adjacency:
                adjacency[edge.target_id].append(edge.source_id)

        start = focal_id if focal_id in adjacency else node_ids[0]

        # BFS to determine depth layers.
        depth: dict[str, int] = {start: 0}
        layers: dict[int, list[str]] = {0: [start]}
        queue: deque[str] = deque([start])
        visited = {start}

        while queue:
            current = queue.popleft()
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    d = depth[current] + 1
                    depth[neighbor] = d
                    layers.setdefault(d, []).append(neighbor)
                    queue.append(neighbor)

        # Assign depth for any disconnected nodes.
        max_depth = max(layers.keys()) if layers else 0
        for nid in node_ids:
            if nid not in depth:
                max_depth += 1
                depth[nid] = max_depth
                layers.setdefault(max_depth, []).append(nid)

        # Compute (x, y) for each node.
        positions: dict[str, tuple[float, float]] = {}
        for layer_idx, layer_nodes in layers.items():
            y = layer_idx * self.y_spacing
            count = len(layer_nodes)
            for col_idx, nid in enumerate(layer_nodes):
                x = (col_idx - (count - 1) / 2.0) * self.x_spacing
                positions[nid] = (x, y)

        result = []
        for node in nodes:
            x, y = positions.get(node.node_id, (0.0, 0.0))
            # Return a copy with updated coordinates.
            updated = type(node)(
                node_id=node.node_id,
                label=node.label,
                kind=node.kind,
                x=x,
                y=y,
                metadata=dict(node.metadata),
            )
            result.append(updated)
        return result

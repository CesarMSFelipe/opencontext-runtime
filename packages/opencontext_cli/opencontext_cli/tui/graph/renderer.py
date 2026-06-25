"""AsciiGraphRenderer — produces a char-grid string from laid-out graph nodes.

Non-TTY / no-TUI fallback: plain text adjacency list.
"""

from __future__ import annotations

from opencontext_cli.tui.graph.models import GraphEdgeView, GraphNodeView


class AsciiGraphRenderer:
    """Renders a positioned graph as ASCII art or plain text."""

    def __init__(self, width: int = 80, height: int = 24) -> None:
        self.width = width
        self.height = height

    def render(
        self,
        nodes: list[GraphNodeView],
        edges: list[GraphEdgeView],
        *,
        text_fallback: bool = False,
    ) -> str:
        """Render the graph.

        When *text_fallback* is True (or terminal is non-TTY), returns a plain
        text adjacency list. Otherwise returns a char-grid ASCII rendering.
        """
        if not nodes:
            return "(empty graph)"

        if text_fallback:
            return self._adjacency_list(nodes, edges)
        return self._char_grid(nodes, edges)

    def _adjacency_list(
        self,
        nodes: list[GraphNodeView],
        edges: list[GraphEdgeView],
    ) -> str:
        """Plain text adjacency list — the no-TUI fallback."""
        adjacency: dict[str, list[str]] = {n.node_id: [] for n in nodes}
        for edge in edges:
            if edge.source_id in adjacency:
                adjacency[edge.source_id].append(edge.target_id)

        lines = ["Graph adjacency list:"]
        for node in nodes:
            neighbors = adjacency.get(node.node_id, [])
            label = node.label or node.node_id
            if neighbors:
                lines.append(f"  {label} -> {', '.join(neighbors)}")
            else:
                lines.append(f"  {label}")
        return "\n".join(lines)

    def _char_grid(
        self,
        nodes: list[GraphNodeView],
        edges: list[GraphEdgeView],
    ) -> str:
        """ASCII char-grid using node (x, y) coordinates."""
        if not nodes:
            return ""

        # Determine coordinate bounds.
        xs = [n.x for n in nodes]
        ys = [n.y for n in nodes]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        x_range = max(max_x - min_x, 1.0)
        y_range = max(max_y - min_y, 1.0)

        # Reserve 1 cell margin.
        usable_w = max(self.width - 2, 4)
        usable_h = max(self.height - 2, 4)

        def to_grid(x: float, y: float) -> tuple[int, int]:
            gx = int((x - min_x) / x_range * usable_w)
            gy = int((y - min_y) / y_range * usable_h)
            return min(gx, usable_w), min(gy, usable_h)

        grid = [[" " for _ in range(usable_w + 1)] for _ in range(usable_h + 1)]

        # Draw nodes (first char of label at position).
        node_positions: dict[str, tuple[int, int]] = {}
        for node in nodes:
            gx, gy = to_grid(node.x, node.y)
            node_positions[node.node_id] = (gx, gy)
            label_char = (node.label or node.node_id)[:1]
            if 0 <= gy < len(grid) and 0 <= gx < len(grid[0]):
                grid[gy][gx] = label_char

        # Draw edges as '*' midpoints.
        for edge in edges:
            if edge.source_id in node_positions and edge.target_id in node_positions:
                sx, sy = node_positions[edge.source_id]
                tx, ty = node_positions[edge.target_id]
                mx, my = (sx + tx) // 2, (sy + ty) // 2
                if 0 <= my < len(grid) and 0 <= mx < len(grid[0]):
                    if grid[my][mx] == " ":
                        grid[my][mx] = "-"

        return "\n".join("".join(row) for row in grid)

"""GraphViewport — pan and zoom state for the graph canvas."""

from __future__ import annotations

from dataclasses import dataclass, field

from opencontext_cli.tui.graph.models import GraphMode


@dataclass
class GraphViewport:
    """Tracks pan offset and zoom level for the graph canvas.

    pan_x, pan_y: signed offset in grid units.
    zoom: scale factor (1.0 = default, >1.0 = zoomed in, <1.0 = zoomed out).
    mode: current display mode filter.
    """

    pan_x: float = 0.0
    pan_y: float = 0.0
    zoom: float = 1.0
    mode: GraphMode = GraphMode.RUN

    # NOTE: Zoom clamps to prevent degenerate scales.
    _zoom_min: float = field(default=0.25, init=False, repr=False)
    _zoom_max: float = field(default=4.0, init=False, repr=False)

    def pan(self, dx: float, dy: float) -> GraphViewport:
        """Return a new viewport offset by (dx, dy)."""
        return GraphViewport(
            pan_x=self.pan_x + dx,
            pan_y=self.pan_y + dy,
            zoom=self.zoom,
            mode=self.mode,
        )

    def zoom_in(self, factor: float = 1.25) -> GraphViewport:
        """Return a new viewport zoomed in by *factor*."""
        new_zoom = min(self.zoom * factor, self._zoom_max)
        return GraphViewport(pan_x=self.pan_x, pan_y=self.pan_y, zoom=new_zoom, mode=self.mode)

    def zoom_out(self, factor: float = 1.25) -> GraphViewport:
        """Return a new viewport zoomed out by *factor*."""
        new_zoom = max(self.zoom / factor, self._zoom_min)
        return GraphViewport(pan_x=self.pan_x, pan_y=self.pan_y, zoom=new_zoom, mode=self.mode)

    def set_mode(self, mode: GraphMode) -> GraphViewport:
        """Return a new viewport with the given display mode."""
        return GraphViewport(pan_x=self.pan_x, pan_y=self.pan_y, zoom=self.zoom, mode=mode)

    def effective_width(self, base_width: int) -> int:
        """Return the effective render width after zoom."""
        return max(4, int(base_width * self.zoom))

    def effective_height(self, base_height: int) -> int:
        """Return the effective render height after zoom."""
        return max(4, int(base_height * self.zoom))

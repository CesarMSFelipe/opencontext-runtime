"""GraphScreen — interactive graph TUI screen.

Loads graph data for a run or knowledge graph and renders it via GraphCanvas.
Text adjacency-list fallback is available via ``--no-tui`` / non-TTY.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, ClassVar

from opencontext_cli.tui.graph.models import (
    GraphEdgeView,
    GraphMode,
    GraphNodeKind,
    GraphNodeView,
    GraphViewState,
)

# NOTE: Guard Textual import — missing textual must not prevent CLI startup.
try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.screen import Screen
    from textual.widgets import Footer, Header

    _TEXTUAL_AVAILABLE = True
except ImportError:
    Screen = object  # type: ignore[assignment, misc]
    ComposeResult = Any  # type: ignore[assignment]
    Binding = object  # type: ignore[assignment]
    _TEXTUAL_AVAILABLE = False


class GraphScreen(Screen):  # type: ignore[misc, valid-type]
    """Full-screen interactive graph display."""

    BINDINGS: ClassVar[list] = [
        Binding("escape,q", "dismiss", "Back"),
    ]

    DEFAULT_CSS = """
    GraphScreen { background: #0B0F14; color: #E6EDF3; padding: 1 2; }
    #graph-content { height: 1fr; }
    """

    def __init__(
        self,
        view_state: GraphViewState | None = None,
        title: str = "Graph",
        **kwargs: Any,
    ) -> None:
        if _TEXTUAL_AVAILABLE:
            super().__init__(**kwargs)
        self._view_state = view_state or GraphViewState(nodes=[], edges=[])
        self._title = title
        self._no_tui = not sys.stdout.isatty()

    def compose(self) -> ComposeResult:  # type: ignore[misc]
        if _TEXTUAL_AVAILABLE:
            from opencontext_cli.tui.widgets.graph_canvas import GraphCanvas

            yield Header(show_clock=False)
            canvas = GraphCanvas(
                nodes=self._view_state.nodes,
                edges=self._view_state.edges,
                mode=self._view_state.mode,
                id="graph-content",
            )
            yield canvas
            yield Footer()
        else:
            yield type("Static", (), {"__init__": lambda s, *a, **kw: None})()  # type: ignore

    def render_text(self) -> str:
        """Render the graph as plain text — available in non-TTY / --no-tui mode."""
        from opencontext_cli.tui.graph.renderer import AsciiGraphRenderer

        renderer = AsciiGraphRenderer()
        return renderer.render(
            self._view_state.nodes,
            self._view_state.edges,
            text_fallback=True,
        )


def load_graph_for_run(run_id: str, root: Path | str = ".") -> GraphViewState:
    """Load graph data for an oc-new run from the store.

    Returns a GraphViewState with phase nodes and their transitions as edges.
    Falls back to an empty GraphViewState when the run is not found.
    """
    try:
        from opencontext_core.oc_new.store import OcNewStore

        store = OcNewStore(Path(root))
        state = store.load(run_id)
        nodes = [
            GraphNodeView(
                node_id=phase.name,
                label=phase.name,
                kind=GraphNodeKind.PHASE,
                metadata={"status": phase.status},
            )
            for phase in state.phases
        ]
        edges = []
        for i in range(len(nodes) - 1):
            edges.append(
                GraphEdgeView(
                    source_id=nodes[i].node_id,
                    target_id=nodes[i + 1].node_id,
                    label="next",
                )
            )
        return GraphViewState.build(nodes, edges, mode=GraphMode.RUN)
    except Exception:
        return GraphViewState(nodes=[], edges=[], mode=GraphMode.RUN)


def load_graph_for_kg(root: Path | str = ".") -> GraphViewState:
    """Load graph data from the knowledge graph JSON snapshot.

    Returns a GraphViewState with KG nodes (capped at 60).
    Falls back to an empty GraphViewState when the KG file is not found.
    """
    import json

    try:
        kg_path = Path(root) / ".opencontext" / "knowledge_graph.json"
        if not kg_path.exists():
            return GraphViewState(nodes=[], edges=[], mode=GraphMode.KG)

        data = json.loads(kg_path.read_text(encoding="utf-8"))
        raw_nodes = []
        raw_edges = []

        if isinstance(data, dict):
            raw_nodes = data.get("nodes", [])
            raw_edges = data.get("edges", [])
        elif isinstance(data, list):
            raw_nodes = data

        nodes = []
        for item in raw_nodes:
            if isinstance(item, dict):
                nid = str(item.get("id", item.get("path", "")))
                label = str(item.get("label", item.get("name", nid)))
                nodes.append(GraphNodeView(node_id=nid, label=label, kind=GraphNodeKind.FILE))

        edges = []
        for item in raw_edges:
            if isinstance(item, dict):
                src = str(item.get("source", item.get("from", "")))
                tgt = str(item.get("target", item.get("to", "")))
                if src and tgt:
                    edges.append(GraphEdgeView(source_id=src, target_id=tgt))

        return GraphViewState.build(nodes, edges, mode=GraphMode.KG)
    except Exception:
        return GraphViewState(nodes=[], edges=[], mode=GraphMode.KG)

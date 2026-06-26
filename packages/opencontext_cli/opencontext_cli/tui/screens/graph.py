"""GraphScreen — interactive graph TUI screen.

Loads graph data for a run or knowledge graph and renders it via GraphCanvas.
Text adjacency-list fallback is available via ``--no-tui`` / non-TTY.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header

from opencontext_cli.tui.graph.models import (
    GraphEdgeView,
    GraphMode,
    GraphNodeKind,
    GraphNodeView,
    GraphViewState,
)

# NOTE: Maps KG node kind strings → GraphNodeKind enum; unknown → FILE default.
_KIND_MAP: dict[str, GraphNodeKind] = {
    "file": GraphNodeKind.FILE,
    "symbol": GraphNodeKind.SYMBOL,
    "memory": GraphNodeKind.MEMORY,
    "agent": GraphNodeKind.AGENT,
    "phase": GraphNodeKind.PHASE,
    "unknown": GraphNodeKind.UNKNOWN,
}


def _map_kind(raw: str) -> GraphNodeKind:
    """Return the GraphNodeKind for *raw*, defaulting to FILE for unknown values."""
    return _KIND_MAP.get(raw, GraphNodeKind.FILE)


class GraphScreen(Screen[None]):
    """Full-screen interactive graph display."""

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
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
        *,
        mode: GraphMode = GraphMode.RUN,
        root: Path | str = ".",
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        # When no explicit view_state is given, load it from disk by mode:
        # RUN+run_id → the oc-new run graph; KG → the knowledge graph; else empty.
        if view_state is None:
            if mode == GraphMode.RUN and run_id:
                view_state = load_graph_for_run(run_id, root=root)
            elif mode == GraphMode.KG:
                view_state = load_graph_for_kg(root=root)
            else:
                view_state = GraphViewState(nodes=[], edges=[], mode=mode)
        self._view_state = view_state
        self._title = title
        self._no_tui = not sys.stdout.isatty()

    def compose(self) -> ComposeResult:
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

    def render_text(self) -> str:
        """Render the graph as plain text — available in non-TTY / --no-tui mode."""
        from opencontext_cli.tui.graph.renderer import AsciiGraphRenderer

        renderer = AsciiGraphRenderer()
        return renderer.render(
            self._view_state.nodes,
            self._view_state.edges,
            text_fallback=True,
        )

    def action_dismiss(self, result: Any = None) -> None:  # type: ignore[override]
        self.app.pop_screen()


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
    """Load graph data from the knowledge graph snapshot.

    Load order:
    1. ``.opencontext/knowledge_graph.json`` (JSON snapshot)
    2. ``.storage/opencontext/context_graph.db`` (SQLite DB via GraphDatabase)
    3. Empty GraphViewState on any failure or absence.

    Returns a GraphViewState with KG nodes (capped at 60).
    """
    import json

    base = Path(root)
    try:
        kg_path = base / ".opencontext" / "knowledge_graph.json"
        if kg_path.exists():
            data = json.loads(kg_path.read_text(encoding="utf-8"))
            raw_nodes = []
            raw_edges: list[Any] = []

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
                    raw_kind = str(item.get("kind", "file"))
                    nodes.append(GraphNodeView(node_id=nid, label=label, kind=_map_kind(raw_kind)))

            edges = []
            for item in raw_edges:
                if isinstance(item, dict):
                    src = str(item.get("source", item.get("from", "")))
                    tgt = str(item.get("target", item.get("to", "")))
                    if src and tgt:
                        edges.append(GraphEdgeView(source_id=src, target_id=tgt))

            return GraphViewState.build(nodes, edges, mode=GraphMode.KG)
    except Exception:
        pass

    # Fallback: load from SQLite knowledge-graph DB.
    try:
        db_path = base / ".storage" / "opencontext" / "context_graph.db"
        if db_path.exists():
            from opencontext_core.indexing.graph_db import GraphDatabase

            db = GraphDatabase(db_path)
            conn = db._connect()
            node_rows = conn.execute("SELECT id, name, kind FROM nodes LIMIT 60").fetchall()
            edge_rows = conn.execute(
                "SELECT source_node_id, target_node_id FROM edges "
                "WHERE target_node_id IS NOT NULL LIMIT 120"
            ).fetchall()

            nodes = [
                GraphNodeView(
                    node_id=str(r["id"]),
                    label=str(r["name"]),
                    kind=_map_kind(str(r["kind"] or "file")),
                )
                for r in node_rows
            ]
            edges = [
                GraphEdgeView(
                    source_id=str(r["source_node_id"]),
                    target_id=str(r["target_node_id"]),
                )
                for r in edge_rows
            ]
            return GraphViewState.build(nodes, edges, mode=GraphMode.KG)
    except Exception:
        pass

    return GraphViewState(nodes=[], edges=[], mode=GraphMode.KG)

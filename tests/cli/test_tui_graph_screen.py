"""GraphScreen (knowledge-graph explorer) — construction + data loaders.

The explorer reads the project's KG SQLite DB; with no graph it degrades to an
empty, non-crashing view.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_cli.tui.graph.models import GraphMode
from opencontext_cli.tui.screens.graph import GraphScreen, load_node_neighbors, pick_focus


def test_graphscreen_constructs() -> None:
    screen = GraphScreen(mode=GraphMode.KG, root=".")
    assert screen._mode == GraphMode.KG


def test_pick_focus_no_graph(tmp_path: Path) -> None:
    assert pick_focus(tmp_path) is None


def test_load_neighbors_no_graph(tmp_path: Path) -> None:
    focus, neighbors = load_node_neighbors("missing", root=tmp_path)
    assert focus is None
    assert neighbors == []


def test_render_text_without_graph_does_not_crash() -> None:
    screen = GraphScreen(mode=GraphMode.KG, root=".")
    assert isinstance(screen.render_text(), str)

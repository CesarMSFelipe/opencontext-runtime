"""KG-008: TUI graph loaders read focus and neighbors from a real KG database.

Exercises the SQLite loader path (pick_focus / load_node_neighbors) against a
populated ``context_graph.db`` — no monkeypatched loaders — so a regression in
the real-DB queries fails here instead of leaving the TUI silently empty.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from opencontext_cli.tui.screens.graph import load_node_neighbors, pick_focus
from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


@pytest.fixture()
def indexed_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    (tmp_path / "mod.py").write_text(
        "def helper():\n    return 1\n\n\ndef runner():\n    return helper()\n",
        encoding="utf-8",
    )
    (tmp_path / "test_mod.py").write_text(
        "from mod import runner\n\n\ndef test_runner():\n    assert runner() == 1\n",
        encoding="utf-8",
    )
    kg = KnowledgeGraph(
        config=KnowledgeGraphConfig(enabled=True, languages=["python"]),
        db_path=tmp_path / ".storage" / "opencontext" / "context_graph.db",
    )
    kg.index_project(tmp_path)
    kg.close()
    return tmp_path


def _node_id(root: Path, name: str) -> str:
    conn = sqlite3.connect(str(root / ".storage" / "opencontext" / "context_graph.db"))
    try:
        row = conn.execute("SELECT id FROM nodes WHERE name = ?", (name,)).fetchone()
        assert row is not None, f"node not indexed: {name}"
        return str(row[0])
    finally:
        conn.close()


def test_pick_focus_returns_connected_node_from_real_db(indexed_root: Path) -> None:
    """KG-008: pick_focus lands on a real, connected node in a populated context_graph.db."""
    focus_id = pick_focus(indexed_root)
    assert focus_id is not None
    focus, neighbors = load_node_neighbors(focus_id, indexed_root)
    assert focus is not None
    assert focus.label
    assert neighbors, "the busiest node must have at least one neighbor"


def test_load_node_neighbors_returns_direction_labelled_edges(indexed_root: Path) -> None:
    """KG-008: load_node_neighbors returns the focus plus neighbors with edge directions."""
    runner_id = _node_id(indexed_root, "runner")
    focus, neighbors = load_node_neighbors(runner_id, indexed_root)
    assert focus is not None
    assert focus.label == "runner"
    by_label = {n.label: n for n in neighbors}
    assert by_label["helper"].direction == "calls"
    assert by_label["helper"].kind == "function"
    assert by_label["test_runner"].direction == "called by"


def test_load_node_neighbors_unknown_id_degrades_to_empty(indexed_root: Path) -> None:
    """KG-008: an id absent from the graph yields (None, []) instead of crashing."""
    focus, neighbors = load_node_neighbors("999999", indexed_root)
    assert focus is None
    assert neighbors == []

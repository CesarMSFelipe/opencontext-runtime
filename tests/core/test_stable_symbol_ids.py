"""Stable KG node identity across incremental re-index.

Before the fix, `nodes.id` was an AUTOINCREMENT integer regenerated on every
`index_file` (delete + re-insert), so a single-file re-index minted brand-new
ids and orphaned every inbound cross-file edge that pointed at a symbol in the
re-indexed file. These tests assert content-derived stable ids and that inbound
cross-file edges survive an incremental re-index.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.call_graph import CallGraphAnalyzer
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph, _stable_symbol_id


@pytest.fixture
def kg(tmp_path: Path) -> KnowledgeGraph:
    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    graph = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    yield graph
    graph.close()


def _node_id(kg: KnowledgeGraph, name: str, file_path: str) -> str | None:
    conn = kg.db._connect()
    row = conn.execute(
        "SELECT id FROM nodes WHERE name = ? AND file_path = ?",
        (name, file_path),
    ).fetchone()
    return row["id"] if row else None


def test_node_id_is_content_derived_stable_id(kg: KnowledgeGraph) -> None:
    """A persisted node's id equals `_stable_symbol_id(...)`, not an autoincrement int."""
    kg.index_file("b.py", "def helper():\n    return 1\n")

    stored = _node_id(kg, "helper", "b.py")
    assert stored is not None
    expected = _stable_symbol_id(kg.project_id, "b.py", "helper", "function")
    assert stored == expected
    # Stable ids are the 16-char hex, never a bare integer.
    assert not str(stored).isdigit()


def test_reindex_unchanged_file_preserves_node_id(kg: KnowledgeGraph) -> None:
    kg.index_file("b.py", "def helper():\n    return 1\n")
    first = _node_id(kg, "helper", "b.py")

    kg.index_file("b.py", "def helper():\n    return 1\n")
    second = _node_id(kg, "helper", "b.py")

    assert first is not None
    assert first == second


def test_reindex_callee_preserves_inbound_cross_file_edge(
    kg: KnowledgeGraph, tmp_path: Path
) -> None:
    """The core defect: re-indexing the callee's file must not orphan inbound edges."""
    (tmp_path / "b.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "a.py").write_text("from b import helper\n\n\ndef caller():\n    return helper()\n")
    kg.index_project(tmp_path)

    helper_id = _node_id(kg, "helper", "b.py")
    assert helper_id is not None

    analyzer = CallGraphAnalyzer(kg.db)
    callers_before = {c["name"] for c in analyzer.get_callers(helper_id)}
    assert "caller" in callers_before

    # Re-index b.py with identical content (incremental single-file re-index).
    kg.index_file("b.py", "def helper():\n    return 1\n")

    helper_id_after = _node_id(kg, "helper", "b.py")
    assert helper_id_after == helper_id  # stable id survives

    callers_after = {c["name"] for c in analyzer.get_callers(helper_id_after)}
    assert "caller" in callers_after  # inbound cross-file edge NOT orphaned


def test_stable_id_is_file_scoped(kg: KnowledgeGraph, tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def run():\n    pass\n")
    (tmp_path / "pkg" / "b.py").write_text("def run():\n    pass\n")
    kg.index_project(tmp_path)

    id_a = _node_id(kg, "run", "pkg/a.py")
    id_b = _node_id(kg, "run", "pkg/b.py")
    assert id_a is not None
    assert id_b is not None
    assert id_a != id_b


def test_reindex_removing_symbol_prunes_only_its_edges(kg: KnowledgeGraph, tmp_path: Path) -> None:
    """Removing a symbol on re-index drops its inbound edge but leaves siblings intact."""
    (tmp_path / "lib.py").write_text(
        "def compute():\n    return 1\n\n\ndef other():\n    return 2\n"
    )
    (tmp_path / "caller.py").write_text(
        "from lib import compute\n\n\ndef run():\n    return compute()\n"
    )
    kg.index_project(tmp_path)

    compute_id = _node_id(kg, "compute", "lib.py")
    assert compute_id is not None
    analyzer = CallGraphAnalyzer(kg.db)
    assert "run" in {c["name"] for c in analyzer.get_callers(compute_id)}

    # Re-index lib.py with compute removed.
    kg.index_file("lib.py", "def other():\n    return 2\n")

    # compute is gone; its inbound edge is pruned (not retargeted).
    assert _node_id(kg, "compute", "lib.py") is None
    conn = kg.db._connect()
    dangling = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE target_node_id = ? AND kind = 'calls'",
        (compute_id,),
    ).fetchone()[0]
    assert dangling == 0
    # The sibling symbol `other` is unaffected and still resolvable.
    assert _node_id(kg, "other", "lib.py") is not None

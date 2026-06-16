"""Deterministic cross-file target resolution.

Before the fix, `_resolve` iterated `global_map` and returned the FIRST same-name
node it encountered, so an ambiguous call target bound to an arbitrary,
iteration-order-dependent node. The resolver must now disambiguate by import /
container / kind, and when genuinely ambiguous it must NOT bind to an arbitrary
node (skip / mark unresolved).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.call_graph import CallGraphAnalyzer
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


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


def _has_edge(kg: KnowledgeGraph, src_id: str, tgt_id: str) -> bool:
    conn = kg.db._connect()
    row = conn.execute(
        "SELECT 1 FROM edges WHERE source_node_id = ? AND target_node_id = ? AND kind = 'calls'",
        (src_id, tgt_id),
    ).fetchone()
    return row is not None


def test_ambiguous_same_name_target_is_not_bound_arbitrarily(
    kg: KnowledgeGraph, tmp_path: Path
) -> None:
    (tmp_path / "x.py").write_text("def save():\n    return 1\n")
    (tmp_path / "y.py").write_text("def save():\n    return 2\n")
    # z.py calls save() with no import disambiguating which one.
    (tmp_path / "z.py").write_text("def run():\n    return save()\n")
    kg.index_project(tmp_path)

    save_x = _node_id(kg, "save", "x.py")
    save_y = _node_id(kg, "save", "y.py")
    run_id = _node_id(kg, "run", "z.py")
    assert save_x is not None
    assert save_y is not None
    assert run_id is not None

    # The ambiguous call must NOT bind to a single arbitrary save (no resolved 'calls' edge).
    assert not _has_edge(kg, run_id, save_x)
    assert not _has_edge(kg, run_id, save_y)


def test_import_disambiguation_is_deterministic(kg: KnowledgeGraph, tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("def save():\n    return 1\n")
    (tmp_path / "y.py").write_text("def save():\n    return 2\n")
    # z.py explicitly imports save from x -> must resolve to x's save, never y's.
    (tmp_path / "z.py").write_text("from x import save\n\n\ndef run():\n    return save()\n")

    def _resolved_caller_files() -> set[str | None]:
        graph = KnowledgeGraph(
            config=KnowledgeGraphConfig(enabled=True, languages=["python"]),
            db_path=tmp_path / "kg_run.db",
        )
        try:
            graph.index_project(tmp_path)
            save_x = _node_id(graph, "save", "x.py")
            run_id = _node_id(graph, "run", "z.py")
            assert save_x is not None
            assert run_id is not None
            analyzer = CallGraphAnalyzer(graph.db)
            callees = analyzer.get_callees(run_id)
            # Return the file_path of each resolved 'save' callee target.
            return {c["file_path"] for c in callees if c["name"] == "save"}
        finally:
            # close() before unlink: nulling _conn first would make close() a
            # no-op, orphaning the open connection and locking the file on Windows.
            graph.close()
            (tmp_path / "kg_run.db").unlink(missing_ok=True)

    run1 = _resolved_caller_files()
    run2 = _resolved_caller_files()
    assert run1 == {"x.py"}
    assert run2 == {"x.py"}  # deterministic across runs


def test_container_disambiguates_same_named_methods(kg: KnowledgeGraph, tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("class A:\n    def process(self):\n        return 1\n")
    (tmp_path / "b.py").write_text("class B:\n    def process(self):\n        return 2\n")
    # main calls A().process() with A imported from a.py.
    (tmp_path / "main.py").write_text(
        "from a import A\n\n\ndef main():\n    return A().process()\n"
    )
    kg.index_project(tmp_path)

    a_process = _node_id(kg, "process", "a.py")
    b_process = _node_id(kg, "process", "b.py")
    main_id = _node_id(kg, "main", "main.py")
    assert a_process is not None
    assert b_process is not None
    assert main_id is not None

    # Must resolve to A.process (a.py), never bind to B.process (b.py).
    assert not _has_edge(kg, main_id, b_process)

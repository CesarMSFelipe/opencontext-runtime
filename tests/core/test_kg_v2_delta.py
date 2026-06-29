"""PR-008 KG v2 incremental delta + cache invalidation (KG-08, KG-CONV)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.graph_delta import GraphDelta
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


def _make_kg(tmp_path: Path) -> KnowledgeGraph:
    return KnowledgeGraph(db_path=str(tmp_path / "kg.db"), project_id="proj")


def test_reindex_delta_lists_added_and_deleted(tmp_path: Path) -> None:
    src = tmp_path / "a.py"
    src.write_text("def old():\n    return 1\n\n\ndef keep():\n    return 2\n", encoding="utf-8")
    kg = _make_kg(tmp_path)
    try:
        kg.index_project(tmp_path)
        before = {row["name"] for row in kg.search("old", limit=10)}
        assert "old" in before

        # Remove `old`, add `new`, keep `keep`.
        src.write_text(
            "def keep():\n    return 2\n\n\ndef new():\n    return 3\n", encoding="utf-8"
        )
        delta = kg.reindex_delta({"a.py"}, tmp_path)

        assert isinstance(delta, GraphDelta)
        assert delta.added_nodes, "a new symbol should be added"
        assert delta.deleted_nodes, "the removed symbol should be deleted"
        assert delta.affected_symbols
        assert "a.py" in delta.affected_files
    finally:
        kg.close()


def test_apply_delta_removes_deleted_nodes(tmp_path: Path) -> None:
    src = tmp_path / "b.py"
    src.write_text("def gone():\n    return 1\n", encoding="utf-8")
    kg = _make_kg(tmp_path)
    try:
        kg.index_project(tmp_path)
        rows = kg.search("gone", limit=10)
        node_ids = [r["id"] for r in rows if r["name"] == "gone"]
        assert node_ids
        delta = GraphDelta(
            deleted_nodes=node_ids, affected_symbols=node_ids, affected_files=["b.py"]
        )
        kg.apply_delta(delta)
        after = [r for r in kg.search("gone", limit=10) if r["name"] == "gone"]
        assert after == []
    finally:
        kg.close()


def test_reindex_delta_fires_cache_invalidation(tmp_path: Path) -> None:
    src = tmp_path / "c.py"
    src.write_text("def f():\n    return 1\n", encoding="utf-8")
    kg = _make_kg(tmp_path)
    received: list[list[str]] = []
    kg.cache_invalidation.register(received.append)
    try:
        kg.index_project(tmp_path)
        src.write_text("def f():\n    return 1\n\n\ndef g():\n    return 2\n", encoding="utf-8")
        kg.reindex_delta({"c.py"}, tmp_path)
        assert received, "a reindex producing a delta must fire an invalidation hook"
        keys = received[-1]
        assert any(k.startswith("kg:file:c.py") for k in keys)
    finally:
        kg.close()


def test_empty_delta_does_not_fire(tmp_path: Path) -> None:
    registry_fired: list[list[str]] = []
    kg = _make_kg(tmp_path)
    kg.cache_invalidation.register(registry_fired.append)
    try:
        empty = GraphDelta()
        kg.apply_delta(empty)
        assert registry_fired == []
    finally:
        kg.close()

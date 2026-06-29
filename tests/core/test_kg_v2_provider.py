"""PR-008 KG v2 KnowledgeProvider conformance (KG-12)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.graph_delta import GraphDelta
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.plugins.knowledge_provider import (
    IndexOptions,
    KgQuery,
    KnowledgeProvider,
    SqliteKnowledgeProvider,
    native_provider,
)


def test_native_provider_satisfies_protocol(tmp_path: Path) -> None:
    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"), project_id="proj")
    try:
        provider = native_provider(kg)
        assert isinstance(provider, SqliteKnowledgeProvider)
        # runtime_checkable Protocol: the native provider exposes the full lifecycle.
        assert isinstance(provider, KnowledgeProvider)
        for method in ("index", "query", "retrieve_subgraph", "apply_delta"):
            assert callable(getattr(provider, method))
    finally:
        kg.close()


def test_provider_index_and_query_roundtrip(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def widget():\n    return 1\n", encoding="utf-8")
    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"), project_id="proj")
    try:
        provider = native_provider(kg)
        result = provider.index(tmp_path, IndexOptions())
        assert result.files_indexed >= 1
        assert result.nodes >= 1

        matches = provider.query(KgQuery(text="widget", limit=5)).matches
        assert any(m["name"] == "widget" for m in matches)

        # apply_delta over an empty delta is a safe no-op.
        provider.apply_delta(GraphDelta())
    finally:
        kg.close()

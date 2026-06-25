"""Tests for KG schema extension (slice 4: kg engineering schema).

The knowledge graph surface in ``opencontext_core.indexing.knowledge_graph``
MUST expose engineering-domain NodeKind and EdgeKind values:

* NodeKind: REQUIREMENT, TASK, TEST, PHASE
* EdgeKind: IMPLEMENTS, VERIFIED_BY, DEPENDS_ON

Adding these values is purely additive — existing NodeKind/EdgeKind strings
and the on-disk SQLite index format MUST remain unchanged.
"""

from __future__ import annotations

from opencontext_core.indexing import knowledge_graph as kg_mod


def test_knowledge_graph_module_exposes_node_kind_enum() -> None:
    assert hasattr(kg_mod, "NodeKind"), "knowledge_graph.NodeKind must be exported"
    NodeKind = kg_mod.NodeKind
    for value in ("REQUIREMENT", "TASK", "TEST", "PHASE"):
        assert hasattr(NodeKind, value), f"NodeKind.{value} missing"


def test_knowledge_graph_module_exposes_edge_kind_enum() -> None:
    assert hasattr(kg_mod, "EdgeKind"), "knowledge_graph.EdgeKind must be exported"
    EdgeKind = kg_mod.EdgeKind
    for value in ("IMPLEMENTS", "VERIFIED_BY", "DEPENDS_ON"):
        assert hasattr(EdgeKind, value), f"EdgeKind.{value} missing"


def test_new_node_kind_values_are_strings() -> None:
    NodeKind = kg_mod.NodeKind
    assert NodeKind.REQUIREMENT == "requirement"
    assert NodeKind.TASK == "task"
    assert NodeKind.TEST == "test"
    assert NodeKind.PHASE == "phase"


def test_new_edge_kind_values_are_strings() -> None:
    EdgeKind = kg_mod.EdgeKind
    assert EdgeKind.IMPLEMENTS == "implements"
    assert EdgeKind.VERIFIED_BY == "verified_by"
    assert EdgeKind.DEPENDS_ON == "depends_on"


def test_existing_index_format_unchanged() -> None:
    """KnowledgeGraph.index_file must continue to accept pre-existing kinds."""
    import tempfile

    from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

    with tempfile.TemporaryDirectory() as tmp:
        graph = KnowledgeGraph(db_path=f"{tmp}/kg.db", project_id="proj-x")
        stats = graph.index_file(
            "sample.py",
            "def hello():\n    return 1\n",
        )
        # Existing parse pipeline untouched: we get nodes for ``hello``.
        assert stats["nodes"] >= 1
        assert stats["parse_mode"] in ("tree_sitter", "regex", "none", "skipped")
        graph.close()

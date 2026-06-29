"""PR-008 KG v2 query layer: planner modes, subgraph budgets, capability link."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.models.kg_v2 import KgNode, KgNodeType, kg_node_id
from opencontext_core.retrieval.query_planner import ContextBudget, KgQueryPlanner
from opencontext_core.retrieval.subgraph import build_context_subgraph


def _kg(tmp_path: Path) -> KnowledgeGraph:
    return KnowledgeGraph(db_path=str(tmp_path / "kg.db"), project_id="proj")


def test_mode_selection_per_node_and_task(tmp_path: Path) -> None:
    kg = _kg(tmp_path)
    try:
        planner = KgQueryPlanner(kg)
        assert planner.plan("x", node="verify").mode == "test_first"
        assert planner.plan("who owns the auth module").mode == "owner_first"
        assert planner.plan("fix the failing regression bug").mode == "failure_first"
        assert planner.plan("explain the design decision rationale").mode == "decision_first"
        assert planner.plan("map the module architecture boundary").mode == "architecture_boundary"
        assert planner.plan("add a helper to Parser").mode == "symbol_first"
    finally:
        kg.close()


def test_capability_degrades_test_first(tmp_path: Path) -> None:
    kg = _kg(tmp_path)
    try:
        # No test runner available -> test_first degrades to symbol_first.
        planner = KgQueryPlanner(kg, available_capabilities=set())
        plan = planner.plan("x", node="verify")
        assert plan.mode == "symbol_first"
        assert plan.degraded_from == "test_first"
        assert "test_first" not in planner.available_modes()

        # With a test runner present, test_first stays available.
        planner2 = KgQueryPlanner(kg, available_capabilities={"pytest"})
        assert planner2.plan("x", node="verify").mode == "test_first"
        assert "test_first" in planner2.available_modes()
    finally:
        kg.close()


def test_test_first_ranks_test_nodes_ahead(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "mod.py").write_text("def target():\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_mod.py").write_text(
        "def test_target():\n    assert target() == 1\n", encoding="utf-8"
    )
    kg = _kg(tmp_path)
    try:
        kg.index_project(tmp_path)
        planner = KgQueryPlanner(kg, available_capabilities={"pytest"})
        plan = planner.plan("target", node="verify", budget=ContextBudget(max_nodes=10))
        assert plan.mode == "test_first"
        sub = planner.retrieve_subgraph(plan)
        assert sub.nodes, "subgraph should contain nodes"
        # A test node must rank ahead of the non-test definition.
        first = sub.nodes[0]
        assert (first.path or "").startswith("tests/") or first.type == KgNodeType.TEST
    finally:
        kg.close()


def test_subgraph_node_budget_caps_and_records_omissions() -> None:
    nodes = [
        KgNode(id=kg_node_id("function", f"f{i}", "a.py"), type=KgNodeType.FUNCTION, name=f"f{i}")
        for i in range(5)
    ]
    sub = build_context_subgraph(nodes, max_nodes=2, max_tokens=100_000)
    assert len(sub.nodes) == 2
    assert len(sub.omitted) == 3
    assert all(o.reason == "node_budget" for o in sub.omitted)
    assert 0.0 <= sub.confidence <= 1.0


def test_subgraph_token_budget_caps_and_records_omissions() -> None:
    nodes = [
        KgNode(id=kg_node_id("function", f"f{i}", "a.py"), type=KgNodeType.FUNCTION, name=f"f{i}")
        for i in range(5)
    ]
    sub = build_context_subgraph(nodes, max_nodes=10, max_tokens=1)
    # First node always kept; the rest omitted under the token budget.
    assert len(sub.nodes) == 1
    assert sub.omitted
    assert all(o.reason == "token_budget" for o in sub.omitted)
    assert sub.token_estimate >= 0

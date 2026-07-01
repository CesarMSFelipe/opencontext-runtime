"""Quick tests for PR-008.c/d/e modules."""

from __future__ import annotations

from datetime import datetime, timezone

from opencontext_core.graph.v2.planner import ContextQueryPlanner, BudgetExceededError, KgQueryPlan
from opencontext_core.graph.v2.retriever import ContextSubgraph
from opencontext_core.graph.v2.capability import CapabilityGraph, OwnerResolver
from opencontext_core.graph.v2.freshness import compute_freshness, compute_confidence
from opencontext_core.graph.v2.events import emit_unknown_owner


def test_planner_within_budget() -> None:
    p = ContextQueryPlanner(ceiling=10000)
    plan = p.plan("auth function", ["function"])
    assert isinstance(plan, KgQueryPlan)

def test_planner_over_budget() -> None:
    p = ContextQueryPlanner(ceiling=10)
    try:
        p.plan("a" * 100)
    except BudgetExceededError:
        return
    raise AssertionError("Expected BudgetExceededError")

def test_subgraph_empty() -> None:
    sg = ContextSubgraph()
    assert sg.tokens_used == 0

def test_owner_resolver_stub() -> None:
    r = OwnerResolver()
    ref = r.resolve("src/x.py")
    assert ref.path == "src/x.py"

def test_freshness_new() -> None:
    fs = compute_freshness(datetime.now(tz=timezone.utc))
    assert fs.score > 0.9

def test_confidence_diverse() -> None:
    evidence = [{"source_type": "code"}, {"source_type": "git"}, {"source_type": "docs"}]
    cs = compute_confidence(evidence)
    assert cs.score > 0.5

def test_unknown_owner_event() -> None:
    evt = emit_unknown_owner("src/missing.py")
    assert evt["event"] == "org.owner.unknown"

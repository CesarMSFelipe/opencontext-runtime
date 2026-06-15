"""RetrievalPlanner must rank candidates with compute_hybrid_score.

Before the fix the planner ordered purely by lexical `score` (the hybrid scorer —
provenance, test-affinity, graph distance, memory failure-boost, token penalty —
was tested but never invoked on the live path). This pins that hybrid ranking is
actually applied.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.models.context import ContextItem, ContextPriority
from opencontext_core.retrieval.contracts import EvidenceRequest, RetrievalSurface
from opencontext_core.retrieval.planner import RetrievalPlanner


class _StubSource:
    name = "stub"

    def __init__(self, items: list[ContextItem]) -> None:
        self._items = items

    def retrieve(self, query: str, limit: int) -> list[ContextItem]:
        return self._items[:limit]


def _item(item_id: str, trust: float) -> ContextItem:
    return ContextItem(
        id=item_id,
        content="def f(): pass",
        source=f"src/{item_id}.py",
        source_type="file",
        priority=ContextPriority.P1,
        tokens=100,
        score=0.5,  # identical lexical score for both candidates
        source_trust=trust,
    )


def test_planner_ranks_by_hybrid_not_lexical_only() -> None:
    # Equal lexical score + equal tokens; ids chosen so a pure (-score, tokens, id)
    # sort would put the LOW-trust item first. Hybrid scoring (provenance weight)
    # must instead rank the HIGH-trust item first.
    low = _item("a_low", trust=0.1)
    high = _item("b_high", trust=0.9)
    planner = RetrievalPlanner([_StubSource([low, high])])

    ranked = planner.retrieve("auth", top_k=5)

    assert ranked[0].id == "b_high", "hybrid ranking (provenance) not applied"


def test_planner_plan_still_produces_evidence(tmp_path: Path) -> None:
    # Regression: plan() must still work end-to-end with hybrid ranking.
    items = [_item("x", 0.8), _item("y", 0.4)]
    planner = RetrievalPlanner([_StubSource(items)])
    plan = planner.plan(
        EvidenceRequest(
            query="auth", root=tmp_path, surface=RetrievalSurface.RUNTIME, max_tokens=1000
        ),
        top_k=5,
    )
    assert [e.id for e in plan.evidence] == ["x", "y"]
    assert plan.trust_decision.status == "sufficient"

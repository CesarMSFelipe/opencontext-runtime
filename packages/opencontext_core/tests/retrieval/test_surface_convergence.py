from __future__ import annotations

from pathlib import Path

from opencontext_core.context.compiler import ContextCompiler
from opencontext_core.models.context import ContextItem, ContextPriority, DataClassification
from opencontext_core.retrieval.contracts import EvidenceRequest, RetrievalSurface
from opencontext_core.retrieval.planner import RetrievalPlanner


class EquivalentSurfaceSource:
    name = "fixture"

    def retrieve(self, query: str, limit: int) -> list[ContextItem]:
        assert query == "authenticate users"
        items = [
            ContextItem(
                id="protected:auth-service",
                content="class AuthService: pass",
                source="src/auth.py",
                source_type="file",
                priority=ContextPriority.P1,
                tokens=4,
                score=0.88,
                metadata={"freshness": "current", "protected": True},
                classification=DataClassification.INTERNAL,
                source_trust=0.9,
            ),
            ContextItem(
                id="readme:auth-overview",
                content="Authentication overview includes token login.",
                source="README.md",
                source_type="file",
                priority=ContextPriority.P2,
                tokens=6,
                score=0.7,
                metadata={"freshness": "current"},
                classification=DataClassification.INTERNAL,
                source_trust=0.8,
            ),
            ContextItem(
                id="low:unrelated",
                content="Unrelated release notes that should be omitted by budget.",
                source="CHANGELOG.md",
                source_type="file",
                priority=ContextPriority.P5,
                tokens=9,
                score=0.1,
                metadata={"freshness": "current"},
                classification=DataClassification.INTERNAL,
                source_trust=0.4,
            ),
        ]
        return items[:limit]


def _request(surface: RetrievalSurface, root: Path) -> EvidenceRequest:
    return EvidenceRequest(
        query="authenticate users",
        root=root,
        surface=surface,
        max_tokens=10,
        risk_level="normal",
    )


def _compiler() -> ContextCompiler:
    return ContextCompiler()


def test_equivalent_surfaces_compile_the_same_ranked_evidence(tmp_path: Path) -> None:
    planner = RetrievalPlanner([EquivalentSurfaceSource()])
    compiler = _compiler()

    compiled = {
        surface: compiler.compile(planner.plan(_request(surface, tmp_path), top_k=3))
        for surface in (
            RetrievalSurface.RUNTIME,
            RetrievalSurface.API,
            RetrievalSurface.WORKFLOW,
            RetrievalSurface.AGENT_TOOL,
        )
    }

    source_order = {
        surface: [item.source for item in pack.included] for surface, pack in compiled.items()
    }

    assert set(source_order) == {
        RetrievalSurface.RUNTIME,
        RetrievalSurface.API,
        RetrievalSurface.WORKFLOW,
        RetrievalSurface.AGENT_TOOL,
    }
    assert len({tuple(sources) for sources in source_order.values()}) == 1
    assert source_order[RetrievalSurface.RUNTIME] == ["src/auth.py", "README.md"]
    assert all(
        item.metadata["evidence"]["request_surface"] == surface.value
        for surface, pack in compiled.items()
        for item in pack.included
    )


def test_context_compiler_preserves_protected_priority_and_omission_reasons(
    tmp_path: Path,
) -> None:
    planner = RetrievalPlanner([EquivalentSurfaceSource()])
    plan = planner.plan(_request(RetrievalSurface.RUNTIME, tmp_path), top_k=3)

    pack = _compiler().compile(plan)

    assert [item.id for item in pack.included] == [
        "protected:auth-service",
        "readme:auth-overview",
    ]
    assert pack.included[0].metadata["evidence"]["protected"] is True
    assert [omission.reason for omission in pack.omissions] == ["token_budget_exceeded"]
    assert [item.source for item in pack.omitted] == ["CHANGELOG.md"]

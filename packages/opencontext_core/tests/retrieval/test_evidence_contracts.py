from __future__ import annotations

from pathlib import Path

from opencontext_core.models.context import ContextItem, ContextPriority, DataClassification
from opencontext_core.retrieval.contracts import (
    EvidenceItem,
    EvidencePlan,
    EvidenceRequest,
    FreshnessStatus,
    RetrievalSurface,
    TrustDecision,
)
from opencontext_core.retrieval.planner import RetrievalPlanner
from opencontext_core.retrieval.sources import AdapterPolicy, ManifestFallbackSource


def test_evidence_request_and_plan_preserve_traceable_contract_fields(tmp_path: Path) -> None:
    request = EvidenceRequest(
        query="planner contracts",
        root=tmp_path,
        surface=RetrievalSurface.RUNTIME,
        max_tokens=800,
        risk_level="high",
        refresh_policy="verify",
        trace_parent="trace-parent-1",
    )
    evidence = EvidenceItem(
        id="file:planner.py",
        content="Planner contract source",
        source="packages/opencontext_core/opencontext_core/retrieval/planner.py",
        source_type="file",
        provenance={"retrieval_source": "manifest"},
        confidence=0.86,
        freshness=FreshnessStatus.CURRENT,
        surface=RetrievalSurface.RUNTIME,
        tokens=6,
    )
    plan = EvidencePlan(
        request=request,
        evidence=[evidence],
        fallback_actions=[],
        trust_decision=TrustDecision(status="sufficient", reason="current evidence"),
        trace_id="trace-1",
        omissions=[],
        source_surfaces=[RetrievalSurface.RUNTIME],
    )

    assert plan.request.query == "planner contracts"
    assert plan.evidence[0].provenance == {"retrieval_source": "manifest"}
    assert plan.evidence[0].confidence == 0.86
    assert plan.evidence[0].freshness is FreshnessStatus.CURRENT
    assert plan.source_surfaces == [RetrievalSurface.RUNTIME]


def test_planner_marks_high_risk_unknown_freshness_as_insufficient(tmp_path: Path) -> None:
    class UnknownFreshnessSource:
        name = "graph"

        def retrieve(self, query: str, limit: int) -> list[ContextItem]:
            return [
                ContextItem(
                    id="graph:planner:1",
                    content="Graph-only planner evidence",
                    source="planner.py:1",
                    source_type="graph_symbol",
                    priority=ContextPriority.P1,
                    tokens=4,
                    score=0.91,
                    metadata={"freshness": "unknown", "retrieval_source": "graph"},
                    classification=DataClassification.INTERNAL,
                )
            ]

    request = EvidenceRequest(
        query="planner",
        root=tmp_path,
        surface=RetrievalSurface.AGENT_TOOL,
        max_tokens=400,
        risk_level="high",
    )

    plan = RetrievalPlanner([UnknownFreshnessSource()]).plan(request, top_k=3)

    assert plan.trust_decision.status == "insufficient"
    assert plan.evidence[0].freshness is FreshnessStatus.UNKNOWN
    assert plan.evidence[0].provenance["retrieval_source"] == "graph"
    assert plan.fallback_actions == ["read_source:planner.py:1"]
    assert plan.trace_id.startswith("evidence-plan-")


def test_manifest_fallback_source_runs_without_optional_adapter_policy(
    tmp_path: Path,
) -> None:
    manifest_source = ManifestFallbackSource.from_files(
        root=tmp_path,
        files={"src/planner.py": "def plan_evidence() -> str:\n    return 'ok'\n"},
    )
    disabled_policy = AdapterPolicy(enabled_adapters=[])

    items = manifest_source.retrieve_with_policy("plan_evidence", limit=5, policy=disabled_policy)

    assert [item.source for item in items] == ["src/planner.py"]
    assert items[0].metadata["retrieval_source"] == "manifest"

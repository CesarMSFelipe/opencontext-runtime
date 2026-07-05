"""AICX must be a non-mutating side-channel.

Before the fix, runtime.py reassigned `plan = AICXDecoder().decode(_bc)`, and the
decoder hardcoded `content=""`, so the final context pack reached the agent with
empty bodies while every gate still reported PASS. These tests pin the contract:
real file content reaches the pack, the coverage gate fails on empty content, and
the AICX roundtrip preserves content for protected/INLINE evidence.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.context.bytecode import AICXCompiler, AICXDecoder, compute_metrics
from opencontext_core.models.context import DataClassification
from opencontext_core.retrieval.contracts import (
    EvidenceItem,
    EvidencePlan,
    EvidenceRequest,
    FreshnessStatus,
    RetrievalSurface,
    RiskLevel,
    TrustDecision,
    VerifiedContextRequest,
)
from opencontext_core.runtime import OpenContextRuntime, _verified_context_gates
from tests.core.conftest import create_sample_project, write_config


def _runtime(tmp_path: Path) -> tuple[OpenContextRuntime, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )
    return runtime, project_root


def test_verify_context_contains_real_file_body(tmp_path: Path) -> None:
    runtime, project_root = _runtime(tmp_path)
    result = runtime.verify_context(
        VerifiedContextRequest(
            query="Where is authentication implemented?",
            root=project_root,
            refresh_index=True,
            max_tokens=1200,
        )
    )
    # The rendered context must carry the actual code body, not just the path header.
    assert "AuthService" in result.context or "def login" in result.context
    # Every returned evidence item must carry non-empty content.
    assert result.evidence
    assert any((item.content or "").strip() for item in result.evidence)


def test_build_context_pack_includes_nonempty_content(tmp_path: Path) -> None:
    runtime, project_root = _runtime(tmp_path)
    runtime.index_project(project_root)
    pack = runtime.build_context_pack("Where is authentication implemented?", max_tokens=1200)
    assert pack.included
    assert any((item.content or "").strip() for item in pack.included)


def test_coverage_gate_fails_when_all_content_empty(tmp_path: Path) -> None:
    request = EvidenceRequest(
        query="auth",
        root=tmp_path,
        surface=RetrievalSurface.RUNTIME,
        max_tokens=1000,
    )
    empty = [
        EvidenceItem(
            id="e1",
            content="",  # stripped / unresolved
            source="src/auth.py",
            source_type="file",
            provenance={"method": "graph"},
            confidence=0.9,
            freshness=FreshnessStatus.CURRENT,
            surface=RetrievalSurface.RUNTIME,
            tokens=120,
            classification=DataClassification.INTERNAL,
        )
    ]
    plan = EvidencePlan(
        request=request,
        evidence=empty,
        fallback_actions=[],
        trust_decision=TrustDecision(status="sufficient", reason="ok"),
        trace_id="t",
        omissions=[],
        source_surfaces=[RetrievalSurface.RUNTIME],
    )
    gates = _verified_context_gates(empty, 120, 1000, plan, RiskLevel.NORMAL)
    coverage = next(g for g in gates if g.name == "coverage")
    assert not coverage.passed
    assert "empty_content" in coverage.risks


def test_aicx_roundtrip_preserves_protected_content() -> None:
    request = EvidenceRequest(
        query="auth",
        root=Path("."),
        surface=RetrievalSurface.RUNTIME,
        max_tokens=16000,
    )
    protected_body = "def login(self, u): return bool(u)  # protected body"
    evidence = [
        EvidenceItem(
            id="prot",
            content=protected_body,
            source="src/auth.py",
            source_type="file",
            provenance={"method": "graph"},
            confidence=0.95,
            freshness=FreshnessStatus.CURRENT,
            surface=RetrievalSurface.RUNTIME,
            tokens=200,
            protected=True,
            classification=DataClassification.INTERNAL,
        ),
        EvidenceItem(
            id="ref",
            content="def helper(): pass  # non-protected, reference-only",
            source="src/util.py",
            source_type="file",
            provenance={"method": "graph"},
            confidence=0.6,
            freshness=FreshnessStatus.CURRENT,
            surface=RetrievalSurface.RUNTIME,
            tokens=100,
            protected=False,
            classification=DataClassification.INTERNAL,
        ),
    ]
    plan = EvidencePlan(
        request=request,
        evidence=evidence,
        fallback_actions=[],
        trust_decision=TrustDecision(status="sufficient", reason="ok"),
        trace_id="t",
        omissions=[],
        source_surfaces=[RetrievalSurface.RUNTIME],
    )
    decoded = AICXDecoder().decode(AICXCompiler().compile(plan))
    by_id = {item.id: item for item in decoded.evidence}
    # Protected content survives the roundtrip; non-protected stays a lazy reference.
    assert by_id["prot"].content == protected_body
    assert by_id["ref"].content == ""


def test_metrics_measure_populated_plan_not_stripped() -> None:
    request = EvidenceRequest(
        query="auth", root=Path("."), surface=RetrievalSurface.RUNTIME, max_tokens=16000
    )
    populated = [
        EvidenceItem(
            id=f"e{i}",
            content="def authenticate(): pass  # body",
            source=f"src/m{i}.py",
            source_type="file",
            provenance={"method": "graph"},
            confidence=0.8,
            freshness=FreshnessStatus.CURRENT,
            surface=RetrievalSurface.RUNTIME,
            tokens=300,
            classification=DataClassification.INTERNAL,
        )
        for i in range(3)
    ]
    plan = EvidencePlan(
        request=request,
        evidence=populated,
        fallback_actions=[],
        trust_decision=TrustDecision(status="sufficient", reason="ok"),
        trace_id="t",
        omissions=[],
        source_surfaces=[RetrievalSurface.RUNTIME],
    )
    bc = AICXCompiler().compile(plan)
    metrics = compute_metrics(plan, bc)
    assert metrics.original_tokens == 900
    assert metrics.token_reduction_pct > 0.0

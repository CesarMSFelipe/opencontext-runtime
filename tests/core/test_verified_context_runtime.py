from __future__ import annotations

from pathlib import Path

import pytest

from conftest import create_sample_project, write_config
from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.memory_usability.context_repository import ContextRepository
from opencontext_core.models.context import CompressionStrategy, ContextItem, ContextPriority
from opencontext_core.retrieval.contracts import (
    EvidenceRequest,
    RetrievalSurface,
    RiskLevel,
    VerifiedContextRequest,
)
from opencontext_core.retrieval.planner import RetrievalPlanner
from opencontext_core.runtime import OpenContextRuntime


def test_verified_context_request_rejects_empty_query() -> None:
    with pytest.raises(ValueError, match="query"):
        VerifiedContextRequest(query=" ", max_tokens=100)


def test_verified_context_request_rejects_invalid_budget() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        VerifiedContextRequest(query="Where is auth?", max_tokens=0)


def test_runtime_verify_context_returns_complete_traceable_result(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )

    result = runtime.verify_context(
        VerifiedContextRequest(
            query="Where is authentication implemented?",
            root=project_root,
            refresh_index=True,
            max_tokens=1200,
        )
    )

    assert result.trace_id
    assert "src/auth.py" in result.context
    assert [item.source for item in result.evidence]
    assert result.memory == []
    assert result.gates
    assert all(gate.name and gate.reason for gate in result.gates)
    assert any(gate.name == "provenance" for gate in result.gates)
    assert result.risk_level is RiskLevel.NORMAL
    assert result.trust_decision.status in {"sufficient", "insufficient"}
    assert result.token_usage["final_context_pack"] <= 1200
    assert "vector_disabled" in result.omitted_sources


def test_normal_risk_query_does_not_fail_policy_gate_as_high_risk(tmp_path: Path) -> None:
    """The policy gate must be consistent with the reported risk.

    Regression: the plan's trust was computed with a provisional risk (assuming 0
    evidence), so a query reported as NORMAL could still fail the policy gate
    citing "high-risk evidence requires explicit source fallback", and the CLI
    would exit non-zero on a perfectly good result.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )

    result = runtime.verify_context(
        VerifiedContextRequest(
            query="Where is authentication implemented?",
            root=project_root,
            refresh_index=True,
        )
    )

    assert result.risk_level is RiskLevel.NORMAL
    assert result.evidence  # evidence was retrieved
    policy = next(g for g in result.gates if g.name == "policy")
    assert policy.passed, f"policy gate failed on a normal-risk result: {policy.reason}"
    assert "high-risk" not in policy.reason


def test_runtime_verify_context_includes_local_memory_when_enabled(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    ContextRepository(project_root).store(
        "Authentication decision: AuthService owns login flow.",
        kind="decision",
        source="manual:test",
        pin=True,
        memory_id="auth-memory",
    )
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )

    result = runtime.verify_context(
        VerifiedContextRequest(
            query="Where is authentication implemented?",
            root=project_root,
            refresh_index=True,
            max_tokens=1200,
            include_memory=True,
        )
    )

    assert [item.id for item in result.memory] == ["memory:auth-memory"]
    assert result.memory[0].provenance["source"] == "manual:test"


def test_runtime_verify_context_reports_memory_omission_when_disabled(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    ContextRepository(project_root).store(
        "Authentication decision: AuthService owns login flow.",
        kind="decision",
        source="manual:test",
        pin=True,
        memory_id="auth-memory",
    )
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )

    result = runtime.verify_context(
        VerifiedContextRequest(
            query="Where is authentication implemented?",
            root=project_root,
            refresh_index=True,
            max_tokens=1200,
            include_memory=False,
        )
    )

    assert result.memory == []
    assert "memory_disabled" in result.omitted_sources


def test_runtime_verify_context_marks_sensitive_empty_evidence_high_risk(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    runtime = OpenContextRuntime(
        config_path=write_config(tmp_path, project_root),
        storage_path=tmp_path / ".storage/opencontext",
    )

    result = runtime.verify_context(
        VerifiedContextRequest(
            query="Change secret token handling",
            root=project_root,
            refresh_index=False,
            max_tokens=1200,
        )
    )

    assert result.risk_level is RiskLevel.HIGH
    assert any(not gate.passed for gate in result.gates)
    assert result.trust_decision.status == "insufficient"


def test_safe_compression_preserves_protected_span() -> None:
    config = OpenContextConfig.model_validate(default_config_data()).context.compression
    engine = CompressionEngine(config)
    content = "keep this citation [AUTH-1] " + "filler " * 400
    item = ContextItem(
        id="protected",
        source="doc.md",
        source_type="file",
        content=content,
        priority=ContextPriority.P1,
        tokens=500,
        score=1.0,
    )

    result = engine.compress_item(item)

    assert "[AUTH-1]" in result.item.content
    assert result.strategy is CompressionStrategy.NONE
    assert result.item.metadata["compression"]["reason"] == "protected_spans_detected"


def test_retrieval_planner_reports_optional_source_omission(tmp_path: Path) -> None:
    class BrokenSource:
        name = "memory"

        def retrieve(self, query: str, limit: int) -> list[ContextItem]:
            raise RuntimeError("offline")

    planner = RetrievalPlanner([BrokenSource()])

    plan = planner.plan(
        EvidenceRequest(
            query="auth",
            root=tmp_path,
            surface=RetrievalSurface.RUNTIME,
            max_tokens=100,
        ),
        top_k=5,
    )

    assert plan.omissions == ["memory_unavailable"]
    assert plan.trust_decision.status == "insufficient"

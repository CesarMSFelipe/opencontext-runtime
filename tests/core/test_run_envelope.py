"""Tests for RunEnvelope and sub-models."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from opencontext_core.compat import UTC
from opencontext_core.models.run_envelope import (
    ArtifactRef,
    ModelUse,
    PolicyDecision,
    RunEnvelope,
    ToolCallRecord,
)


def test_run_envelope_minimal():
    env = RunEnvelope(
        run_id="r1",
        workflow_id="wf1",
        task="fix auth",
        status="planned",
    )
    assert env.schema_version == "opencontext.run_envelope.v1"
    assert env.tool_calls == []
    assert env.artifacts == []


def test_run_envelope_schema_version_exact():
    env = RunEnvelope(run_id="r", workflow_id="w", task="t", status="passed")
    assert env.schema_version == "opencontext.run_envelope.v1"


def test_run_envelope_round_trip():
    env = RunEnvelope(
        run_id="r1",
        workflow_id="wf1",
        task="test",
        status="passed",
        tool_calls=[ToolCallRecord(tool="opencontext_search", status="passed")],
        artifacts=[ArtifactRef(kind="spec", path="/tmp/spec.md")],
        model_uses=[ModelUse(phase="explore")],
        warnings=["warn1"],
    )
    dumped = env.model_dump()
    restored = RunEnvelope.model_validate(dumped)
    assert restored.run_id == "r1"
    assert len(restored.tool_calls) == 1
    assert len(restored.artifacts) == 1
    assert restored.warnings == ["warn1"]


def test_run_envelope_extra_field_rejected():
    with pytest.raises(ValidationError):
        RunEnvelope(run_id="r", workflow_id="w", task="t", status="passed", unknown="x")


def test_model_use_extra_rejected():
    with pytest.raises(ValidationError):
        ModelUse(phase="explore", unknown_field="bad")


def test_tool_call_record_fields():
    tc = ToolCallRecord(tool="opencontext_search", status="denied")
    assert tc.tool == "opencontext_search"
    assert tc.status == "denied"
    assert tc.warnings == []


def test_policy_decision_fields():
    pd = PolicyDecision(
        id="pd1",
        subject="opencontext_run",
        operation="execute",
        decision="denied",
        reason="not_allowlisted",
        policy="ToolPermissionPolicy",
    )
    assert pd.decision == "denied"
    assert pd.metadata == {}


def test_artifact_ref_fields():
    ar = ArtifactRef(kind="report", path="/tmp/report.json")
    assert ar.sha256 is None
    assert ar.metadata == {}


def test_datetime_serializes_to_str():
    env = RunEnvelope(run_id="r", workflow_id="w", task="t", status="running")
    dumped = env.model_dump(mode="json")
    assert isinstance(dumped["created_at"], str)
    datetime.fromisoformat(dumped["created_at"])


def test_updated_at_present():
    env = RunEnvelope(run_id="r", workflow_id="w", task="t", status="failed")
    assert env.updated_at is not None


def test_run_envelope_contract_defaults_none():
    env = RunEnvelope(run_id="r", workflow_id="w", task="t", status="planned")
    assert env.contract is None


def test_run_envelope_carries_contract_round_trip():
    from opencontext_core.models.context_contract import ContextContract, VerificationGate

    contract = ContextContract(
        task="fix login",
        task_type="bugfix",
        risk_level="high",
        risk_tier="critical",
        required_symbols=["auth.login"],
        must_verify=[VerificationGate(id="run-tests")],
        token_budget=28000,
    )
    env = RunEnvelope(
        run_id="r1", workflow_id="wf1", task="fix login", status="running", contract=contract
    )
    restored = RunEnvelope.model_validate(env.model_dump())
    assert restored.contract is not None
    assert restored.contract.contract_id == contract.contract_id
    assert restored.contract.schema_version == "opencontext.context_contract.v2"


def test_run_envelope_with_utc_datetime():
    now = datetime.now(tz=UTC)
    env = RunEnvelope(run_id="r", workflow_id="w", task="t", status="passed", created_at=now)
    dumped = env.model_dump(mode="json")
    restored = datetime.fromisoformat(dumped["created_at"])
    assert restored.year == now.year

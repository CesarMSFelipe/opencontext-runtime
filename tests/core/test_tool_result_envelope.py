"""Tests for ToolResultEnvelope and sub-models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.mcp.schemas import (
    ToolPolicyDecision,
    ToolResultEnvelope,
    ToolWarning,
)


def test_envelope_minimal():
    env = ToolResultEnvelope(tool="opencontext_search", status="passed")
    assert env.schema_version == "opencontext.mcp_tool_result.v1"
    assert env.data == {}
    assert env.warnings == []
    assert env.policy is None


def test_envelope_round_trip():
    env = ToolResultEnvelope(
        tool="opencontext_context",
        status="denied",
        policy=ToolPolicyDecision(decision="denied", reason="tool_not_allowlisted"),
        warnings=[ToolWarning(code="gate", message="blocked")],
    )
    d = env.model_dump()
    restored = ToolResultEnvelope.model_validate(d)
    assert restored.tool == "opencontext_context"
    assert restored.status == "denied"
    assert restored.policy is not None
    assert restored.policy.decision == "denied"
    assert len(restored.warnings) == 1


def test_envelope_extra_field_rejected():
    with pytest.raises(ValidationError):
        ToolResultEnvelope(tool="t", status="passed", extra_key="bad")


def test_warning_extra_field_rejected():
    with pytest.raises(ValidationError):
        ToolWarning(code="x", message="y", unknown="z")


def test_policy_decision_extra_rejected():
    with pytest.raises(ValidationError):
        ToolPolicyDecision(decision="allowed", reason="ok", mystery="x")


def test_envelope_schema_version_exact():
    env = ToolResultEnvelope(tool="t", status="passed")
    assert env.schema_version == "opencontext.mcp_tool_result.v1"


def test_all_statuses_valid():
    for status in ("passed", "warning", "failed", "denied", "skipped"):
        env = ToolResultEnvelope(tool="t", status=status)  # type: ignore[arg-type]
        assert env.status == status


def test_denied_envelope_includes_policy():
    env = ToolResultEnvelope(
        tool="opencontext_run",
        status="denied",
        policy=ToolPolicyDecision(decision="denied", reason="not_in_safe_default"),
    )
    d = env.model_dump()
    assert d["policy"]["decision"] == "denied"
    assert d["policy"]["policy"] == "ToolPermissionPolicy"

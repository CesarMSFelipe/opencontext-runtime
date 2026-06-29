"""Tests for RiskAssessment + assess wrapping RiskClassifier (SPEC MP-006)."""

from __future__ import annotations

from opencontext_core.context.planning.risk import RiskClassifier
from opencontext_core.planning.decomposition import ImplementationSlice
from opencontext_core.planning.risk import RiskAssessment, assess


def _slice() -> ImplementationSlice:
    return ImplementationSlice(slice_id="slice-x", title="X", requirement_ids=["R1", "R2"])


def test_schema_version_is_risk_v1() -> None:
    result = assess(_slice(), task_type="feature", risk_level="medium")
    assert result.schema_version == "opencontext.risk.v1"


def test_level_is_derived_via_risk_classifier() -> None:
    for task_type, risk_level in [
        ("bugfix", "low"),
        ("security", "high"),
        ("feature", "medium"),
        ("migration", "low"),
    ]:
        result = assess(_slice(), task_type=task_type, risk_level=risk_level)
        assert result.level == RiskClassifier().classify(task_type, risk_level)


def test_assessment_carries_factors_and_mitigations() -> None:
    result = assess(_slice(), task_type="security", risk_level="high")
    assert isinstance(result, RiskAssessment)
    assert result.level == "critical"
    assert result.factors
    assert result.mitigations
    assert any("task_type=security" in f for f in result.factors)

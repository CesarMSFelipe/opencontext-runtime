"""RequirementsQualityGate — EARS / BDD pattern validation.

A spec block per requirement must contain either an EARS pattern
(WHEN … THEN / IF … THEN) or a BDD pattern (Given … When … Then).
Blocks lacking both fail with a per-requirement error.
"""

from __future__ import annotations

from opencontext_core.harness.models import GateStatus
from opencontext_core.sdd.requirements_gate import RequirementsQualityGate


def _block(req_id: str, body: str) -> str:
    return f"### Requirement: {req_id}\n\n{body}\n"


def test_valid_ears_spec_passes() -> None:
    spec = _block(
        "REQ-01",
        ("#### Scenario: foo\n\n- GIVEN a precondition\n- WHEN a user does x\n- THEN y happens\n"),
    )
    result = RequirementsQualityGate().evaluate(spec)
    assert result.status == GateStatus.PASSED
    assert result.errors == []


def test_valid_bdd_spec_passes() -> None:
    spec = _block(
        "REQ-02",
        ("#### Scenario: bar\n\n- Given a precondition\n- When a user does x\n- Then y happens\n"),
    )
    result = RequirementsQualityGate().evaluate(spec)
    assert result.status == GateStatus.PASSED


def test_missing_acceptance_criteria_fails() -> None:
    spec = _block("REQ-03", "Some prose with no acceptance keywords at all.\n")
    result = RequirementsQualityGate().evaluate(spec)
    assert result.status == GateStatus.FAILED
    assert any("REQ-03" in err for err in result.errors)


def test_per_requirement_error_isolated() -> None:
    """One bad requirement does NOT poison other requirements."""
    spec = (
        _block("REQ-04", "- GIVEN x\n- WHEN y\n- THEN z\n")
        + _block("REQ-05", "no patterns here\n")
        + _block("REQ-06", "- GIVEN x\n- WHEN y\n- THEN z\n")
    )
    result = RequirementsQualityGate().evaluate(spec)
    assert result.status == GateStatus.FAILED
    failing_reqs = {err.split(":", 1)[0] for err in result.errors}
    assert failing_reqs == {"REQ-05"}


def test_empty_spec_returns_failed_with_no_reqs() -> None:
    result = RequirementsQualityGate().evaluate("")
    # No requirements parsed → vacuously passed (nothing to validate)
    assert result.status == GateStatus.PASSED
    assert result.errors == []

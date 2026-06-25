"""PhaseResultEnvelope — phase completion contract.

The envelope is returned by every phase handler. `can_advance()` is the single
gate the conductor checks before promoting to the next phase. Spec mandates
True for `passed`/`warning`; False for every other status (failed/blocked/
halted/pending/running/skipped).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.workflow.phase_result import PhaseResultEnvelope


def _envelope(status: str, **overrides: object) -> PhaseResultEnvelope:
    base: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "change_id": "10-10-agentic-runtime",
        "phase": "apply",
        "status": status,
        "executive_summary": "ok",
        "artifacts": ["apply/report.md"],
        "token_usage": {"input": 100, "output": 50},
        "duration_s": 1.5,
        "error": None,
    }
    base.update(overrides)
    return PhaseResultEnvelope(**base)  # type: ignore[arg-type]


def test_required_fields_present_and_default_optional_error() -> None:
    env = _envelope("passed")
    assert env.run_id == "run-001"
    assert env.change_id == "10-10-agentic-runtime"
    assert env.phase == "apply"
    assert env.status == "passed"
    assert env.duration_s == 1.5
    assert env.error is None
    assert env.artifacts == ["apply/report.md"]
    assert env.token_usage == {"input": 100, "output": 50}


def test_can_advance_returns_true_for_passed() -> None:
    assert _envelope("passed").can_advance() is True


def test_can_advance_returns_true_for_warning() -> None:
    assert _envelope("warning").can_advance() is True


@pytest.mark.parametrize(
    "status",
    ["failed", "blocked", "halted", "pending", "running", "skipped"],
)
def test_can_advance_returns_false_for_non_advance_statuses(status: str) -> None:
    """Triangulation: every non-passed/warning status must deny advancement."""
    assert _envelope(status).can_advance() is False


def test_can_advance_changes_with_status_assignment() -> None:
    """Same envelope, different status → different advancement verdict."""
    env = _envelope("pending")
    assert env.can_advance() is False
    promoted = env.model_copy(update={"status": "passed"})
    assert promoted.can_advance() is True


def test_envelope_rejects_unknown_status() -> None:
    """Spec is closed; mistyped status is rejected at construction."""
    with pytest.raises(ValidationError):
        _envelope("yolo")


def test_envelope_rejects_extra_field() -> None:
    """Spec demands extra=forbid to catch typos."""
    with pytest.raises(ValidationError):
        PhaseResultEnvelope(
            run_id="r",
            change_id="c",
            phase="apply",
            status="passed",
            duration_s=1.0,
            nope="x",  # type: ignore[call-arg]
        )


def test_envelope_error_round_trips_when_set() -> None:
    """Optional `error` propagates verbatim for triage."""
    env = _envelope("failed", error="boom")
    assert env.error == "boom"
    assert env.can_advance() is False


def test_old_envelope_deserializes_without_new_fields() -> None:
    """Old JSON without the 5 new fields deserializes with defaults."""
    import json

    old = {
        "schema_version": "1.0",
        "run_id": "r",
        "change_id": "c",
        "phase": "apply",
        "status": "passed",
        "duration_s": 1.0,
    }
    env = PhaseResultEnvelope.model_validate(old)
    assert env.persona is None
    assert env.skill is None
    assert env.trace_id is None
    assert env.required_artifacts == []
    assert env.missing_artifacts == []


def test_new_envelope_fields_round_trip() -> None:
    """New fields survive serialize→deserialize."""
    env = PhaseResultEnvelope(
        run_id="r",
        change_id="c",
        phase="spec",
        status="passed",
        duration_s=0.5,
        persona="oc-builder",
        trace_id="t1",
        required_artifacts=["spec.md"],
        missing_artifacts=[],
    )
    restored = PhaseResultEnvelope.model_validate_json(env.model_dump_json())
    assert restored.persona == "oc-builder"
    assert restored.trace_id == "t1"
    assert restored.required_artifacts == ["spec.md"]
    assert restored.missing_artifacts == []

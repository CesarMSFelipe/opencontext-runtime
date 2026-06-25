from __future__ import annotations

import types

import pytest

from opencontext_core.workflow.delegation_validator import (
    DelegationValidationError,
    DelegationValidator,
    require_phase_envelope,
    validate_expected_artifacts,
)
from opencontext_core.workflow.phase_result import PhaseResultEnvelope


def _valid_envelope_dict() -> dict:
    return {
        "run_id": "run-1",
        "change_id": "change-1",
        "phase": "verify",
        "status": "passed",
        "duration_s": 1.0,
    }


def _result(envelope=None, metadata=None):
    r = types.SimpleNamespace()
    r.envelope = envelope
    r.metadata = metadata or {}
    return r


class TestRequirePhaseEnvelope:
    def test_raises_when_envelope_none(self):
        with pytest.raises(DelegationValidationError, match="PhaseResultEnvelope"):
            require_phase_envelope(_result())

    def test_raises_when_envelope_in_metadata_is_also_none(self):
        with pytest.raises(DelegationValidationError):
            require_phase_envelope(_result(envelope=None, metadata={}))

    def test_accepts_envelope_from_metadata_key(self):
        result = _result(envelope=None, metadata={"envelope": _valid_envelope_dict()})
        env = require_phase_envelope(result)
        assert isinstance(env, PhaseResultEnvelope)
        assert env.phase == "verify"

    def test_accepts_well_formed_dict(self):
        result = _result(envelope=_valid_envelope_dict())
        env = require_phase_envelope(result)
        assert env.status == "passed"

    def test_accepts_already_validated_envelope_instance(self):
        envelope = PhaseResultEnvelope(**_valid_envelope_dict())
        result = _result(envelope=envelope)
        env = require_phase_envelope(result)
        assert env is envelope

    def test_raises_on_malformed_dict(self):
        result = _result(envelope={"status": "passed"})  # missing required fields
        with pytest.raises(DelegationValidationError, match="Invalid PhaseResultEnvelope"):
            require_phase_envelope(result)


class TestValidateExpectedArtifacts:
    def _envelope(self, artifacts: list[str]) -> PhaseResultEnvelope:
        return PhaseResultEnvelope(
            run_id="r", change_id="c", phase="apply",
            status="passed", duration_s=0.5, artifacts=artifacts,
        )

    def test_returns_empty_when_all_expected_present(self):
        env = self._envelope(["spec.md", "design.md"])
        assert validate_expected_artifacts(env, ["spec.md", "design.md"]) == []

    def test_returns_missing_keys(self):
        env = self._envelope(["spec.md"])
        missing = validate_expected_artifacts(env, ["spec.md", "design.md", "tasks.md"])
        assert sorted(missing) == ["design.md", "tasks.md"]

    def test_returns_all_when_artifacts_empty(self):
        env = self._envelope([])
        assert sorted(validate_expected_artifacts(env, ["a", "b"])) == ["a", "b"]

    def test_returns_empty_when_expected_is_empty(self):
        env = self._envelope(["spec.md"])
        assert validate_expected_artifacts(env, []) == []


class TestDelegationValidator:
    def test_returns_none_when_not_required_and_no_envelope(self):
        validator = DelegationValidator()
        result = validator.validate(_result(), requires_envelope=False)
        assert result is None

    def test_raises_when_required_and_no_envelope(self):
        validator = DelegationValidator()
        with pytest.raises(DelegationValidationError):
            validator.validate(_result(), requires_envelope=True)

    def test_returns_envelope_when_valid(self):
        validator = DelegationValidator()
        result = _result(envelope=_valid_envelope_dict())
        env = validator.validate(result, requires_envelope=True)
        assert isinstance(env, PhaseResultEnvelope)

    def test_raises_on_missing_expected_artifact(self):
        validator = DelegationValidator()
        result = _result(envelope={**_valid_envelope_dict(), "artifacts": ["spec.md"]})
        with pytest.raises(DelegationValidationError, match="missing expected artifacts"):
            validator.validate(result, requires_envelope=True, expected_artifacts=["spec.md", "design.md"])

    def test_passes_when_all_expected_artifacts_present(self):
        validator = DelegationValidator()
        result = _result(envelope={**_valid_envelope_dict(), "artifacts": ["spec.md", "design.md"]})
        env = validator.validate(result, requires_envelope=True, expected_artifacts=["spec.md", "design.md"])
        assert env is not None

"""DelegationValidator — validates sub-agent results at phase boundaries.

Ensures that phases which require a ``PhaseResultEnvelope`` receive one, and
that all expected artifacts are present in the result.  Phases that do not
require an envelope are skipped silently (LOCAL/MOCK delegation leaves
``envelope=None`` and must continue to work without change).
"""

from __future__ import annotations

from typing import Any

from opencontext_core.workflow.phase_result import PhaseResultEnvelope


class DelegationValidationError(RuntimeError):
    """Raised when a sub-agent result fails the delegation contract."""


def require_phase_envelope(result: Any) -> PhaseResultEnvelope:
    """Extract and validate the ``PhaseResultEnvelope`` from a sub-agent result.

    Args:
        result: The result returned by the sub-agent.

    Returns:
        A validated ``PhaseResultEnvelope`` instance.

    Raises:
        DelegationValidationError: If no envelope is present or the envelope
            data is not a valid ``PhaseResultEnvelope``.
    """
    payload = getattr(result, "envelope", None)
    if payload is None:
        meta = getattr(result, "metadata", {}) or {}
        payload = meta.get("envelope")
    if payload is None:
        raise DelegationValidationError(
            "Sub-agent did not return a PhaseResultEnvelope. "
            "Ensure the delegated phase sets result.envelope before returning."
        )
    try:
        if isinstance(payload, PhaseResultEnvelope):
            return payload
        return PhaseResultEnvelope.model_validate(payload)
    except Exception as exc:
        raise DelegationValidationError(f"Invalid PhaseResultEnvelope payload: {exc}") from exc


def validate_expected_artifacts(
    envelope: PhaseResultEnvelope,
    expected: list[str],
) -> list[str]:
    """Return artifact keys declared as required that are absent from the envelope.

    An empty list means all expected artifacts are present.

    Args:
        envelope: The validated phase result envelope.
        expected: Artifact keys that the phase definition declares as required.

    Returns:
        List of missing artifact keys (empty list = all present).
    """
    present: set[str] = set(envelope.artifacts)
    return [a for a in expected if a not in present]


class DelegationValidator:
    """Validates sub-agent results against a phase's delegation contract.

    Usage::

        validator = DelegationValidator()
        validator.validate(result, requires_envelope=True, expected_artifacts=["spec.md"])
    """

    def validate(
        self,
        result: Any,
        *,
        requires_envelope: bool = False,
        expected_artifacts: list[str] | None = None,
    ) -> PhaseResultEnvelope | None:
        """Validate a sub-agent result.

        Args:
            result: The sub-agent result to validate.
            requires_envelope: When True, raise if the result has no envelope.
                When False, skip envelope validation entirely (LOCAL/MOCK paths).
            expected_artifacts: Optional list of artifact keys that must be
                present in the envelope.  Ignored when ``requires_envelope`` is
                False or envelope is absent.

        Returns:
            The validated ``PhaseResultEnvelope`` when present; ``None`` when
            ``requires_envelope`` is False and no envelope was provided.

        Raises:
            DelegationValidationError: If validation fails.
        """
        # Only validate when an envelope is required *and* present. LOCAL/MOCK
        # delegation leaves envelope=None by design — do not penalise those paths.
        has_envelope = getattr(result, "envelope", None) is not None
        if not requires_envelope and not has_envelope:
            return None

        envelope = require_phase_envelope(result)

        if expected_artifacts:
            missing = validate_expected_artifacts(envelope, expected_artifacts)
            if missing:
                raise DelegationValidationError(
                    f"Sub-agent result is missing expected artifacts: {missing}"
                )

        return envelope


__all__ = [
    "DelegationValidationError",
    "DelegationValidator",
    "require_phase_envelope",
    "validate_expected_artifacts",
]

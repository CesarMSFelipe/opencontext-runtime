"""Canonical outcome states and the legacy-status mapping layer.

The runtime accumulated many ad-hoc status strings (``completed``, ``ready``,
``partial``, ...). This module defines the nine canonical product states and a
pure mapping from legacy values onto them. It deliberately does NOT replace
the existing ``PhaseResultStatus``/``RunStatus`` enums — those have too many
dependents; callers translate at the output boundary via :func:`to_canonical`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class CanonicalStatus(StrEnum):
    """The nine canonical outcome states of any OpenContext operation."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_EXECUTOR = "needs_executor"
    NEEDS_APPROVAL = "needs_approval"
    NEEDS_CONTEXT = "needs_context"
    NEEDS_CONFIGURATION = "needs_configuration"
    NOT_APPLICABLE = "not_applicable"
    CANCELLED = "cancelled"


_LEGACY_STATUS_MAP: Final[dict[str, CanonicalStatus]] = {
    "completed": CanonicalStatus.PASSED,
    "warning": CanonicalStatus.PASSED,
    "done": CanonicalStatus.PASSED,
    "done_with_concerns": CanonicalStatus.PASSED,
    "ready": CanonicalStatus.PASSED,
    "halted": CanonicalStatus.BLOCKED,
    "skipped": CanonicalStatus.NOT_APPLICABLE,
    "partial": CanonicalStatus.NEEDS_CONFIGURATION,
    "error": CanonicalStatus.FAILED,
    "policy_blocked": CanonicalStatus.NEEDS_APPROVAL,
    "not_applied": CanonicalStatus.NEEDS_EXECUTOR,
    # OC Flow / run-workflow terminal vocabulary (RUN_STATE_CONTRACT).
    "escalated": CanonicalStatus.FAILED,
    "needs_provider": CanonicalStatus.NEEDS_EXECUTOR,
    "needs_verification": CanonicalStatus.FAILED,
    "needs_user_edit": CanonicalStatus.NEEDS_APPROVAL,
    "tdd_violation": CanonicalStatus.BLOCKED,
    # RuntimeApi._legacy_status harness translations.
    "completed_with_warnings": CanonicalStatus.PASSED,
    "scaffolded": CanonicalStatus.NOT_APPLICABLE,
}


def to_canonical(status: str) -> CanonicalStatus:
    """Map any status string to a canonical state; unknown values fail closed."""
    try:
        return CanonicalStatus(status)
    except ValueError:
        return _LEGACY_STATUS_MAP.get(status, CanonicalStatus.FAILED)


_CANONICAL_EXIT_CODES: Final[dict[CanonicalStatus, int]] = {
    CanonicalStatus.PASSED: 0,
    CanonicalStatus.NOT_APPLICABLE: 0,
    CanonicalStatus.FAILED: 1,
    CanonicalStatus.BLOCKED: 1,
    CanonicalStatus.NEEDS_CONTEXT: 1,
    CanonicalStatus.CANCELLED: 1,
    CanonicalStatus.NEEDS_CONFIGURATION: 3,
    CanonicalStatus.NEEDS_APPROVAL: 4,
    CanonicalStatus.NEEDS_EXECUTOR: 5,
}


def exit_code_for_run(
    status: str,
    *,
    tdd_violation: bool = False,
    verification_failed: bool = False,
) -> int:
    """Pure exit-code derivation for workflow runs (RUN_STATE / CLI contracts).

    A TDD strict violation exits 6 and a failed verification exits 8; both are
    more specific than the base canonical mapping and only apply to non-passing
    outcomes. Unknown statuses fail closed (1).
    """
    canonical = to_canonical(str(status))
    if tdd_violation and canonical is not CanonicalStatus.PASSED:
        return 6
    if verification_failed and canonical is CanonicalStatus.FAILED:
        return 8
    return _CANONICAL_EXIT_CODES.get(canonical, 1)

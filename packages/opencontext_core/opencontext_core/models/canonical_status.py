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
}


def to_canonical(status: str) -> CanonicalStatus:
    """Map any status string to a canonical state; unknown values fail closed."""
    try:
        return CanonicalStatus(status)
    except ValueError:
        return _LEGACY_STATUS_MAP.get(status, CanonicalStatus.FAILED)

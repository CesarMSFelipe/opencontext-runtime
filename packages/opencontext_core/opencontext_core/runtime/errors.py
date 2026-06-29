"""Typed runtime errors for the Runtime Core (SPEC RC-012).

Defines the ``RuntimeErrorCode`` taxonomy from
``02-runtime-architecture.md`` §27 and a ``RuntimeFailure`` exception that
carries the required fields: message, recoverability, next recommended action,
evidence refs, and a user-facing summary.
"""

from __future__ import annotations

from opencontext_core.compat import StrEnum
from opencontext_core.errors import OpenContextError


class RuntimeErrorCode(StrEnum):
    """Typed runtime error codes (book §27, 9 codes)."""

    WORKFLOW_NOT_FOUND = "workflow_not_found"
    INVALID_TRANSITION = "invalid_transition"
    POLICY_DENIED = "policy_denied"
    CAPABILITY_MISSING = "capability_missing"
    OUTPUT_CONTRACT_FAILED = "output_contract_failed"
    MUTATION_FAILED = "mutation_failed"
    INSPECTION_FAILED = "inspection_failed"
    PROVIDER_FAILED = "provider_failed"
    RESUME_FAILED = "resume_failed"


class RuntimeFailure(OpenContextError):
    """A typed, recoverable-or-not runtime error.

    Subclasses the shared :class:`OpenContextError` base so existing
    ``except OpenContextError`` handlers keep working, while adding the typed
    code and recovery metadata the runtime contract requires.
    """

    def __init__(
        self,
        code: RuntimeErrorCode,
        message: str,
        *,
        recoverable: bool,
        next_action: str | None = None,
        evidence_refs: list[str] | None = None,
        user_summary: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recoverable = recoverable
        self.next_action = next_action
        self.evidence_refs: list[str] = list(evidence_refs or [])
        # A user-facing summary is always present; default to the message.
        self.user_summary = user_summary or message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

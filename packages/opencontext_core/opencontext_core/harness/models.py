"""Data models for the Harness system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from opencontext_core.compat import StrEnum


class BudgetMode(StrEnum):
    """Token budget enforcement mode."""

    OFF = "off"
    WARN = "warn"
    STRICT = "strict"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}.{self.name}>"


class PrivacyProfile(StrEnum):
    """Privacy enforcement profile — opt-in."""

    OFF = "off"
    STANDARD = "standard"
    RESTRICTED = "restricted"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}.{self.name}>"


class GateStatus(StrEnum):
    """Status of a phase gate evaluation."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}.{self.name}>"

    @property
    def is_ok(self) -> bool:
        """True if status is PASSED or SKIPPED (not blocking)."""
        return self in (GateStatus.PASSED, GateStatus.SKIPPED)


class PermissionScope(StrEnum):
    """Scope of operations that can be restricted by a privacy rule."""

    EXTERNAL_CALLS = "external_calls"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    SECRET_ACCESS = "secret_access"
    NETWORK_CALL = "network_call"


class DataClassification(StrEnum):
    """Data classification levels for privacy rules."""

    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    CONFIDENTIAL = "confidential"


class AuditLevel(StrEnum):
    """Audit level for privacy rule enforcement."""

    NONE = "none"
    BASIC = "basic"
    DETAILED = "detailed"


class PrivacyRule(BaseModel):
    """A privacy rule that restricts operations based on provider and scope."""

    id: str
    name: str
    description: str
    permission_scopes: list[PermissionScope]
    data_classification: DataClassification
    provider_restrictions: list[str] = []
    audit_level: AuditLevel = AuditLevel.BASIC

    def evaluate(self, operation: dict[str, Any]) -> bool:
        """Evaluate whether an operation is allowed by this rule.

        Evaluation uses three factors:
        1. Scope match — does the operation's scope match this rule's scopes?
        2. Provider restrictions — is the provider blocked?
        3. Data classification — does the operation's classification meet
           the rule's minimum classification threshold?

        Args:
            operation: Dict with 'provider', 'scope', and optionally
                'data_classification' keys describing the operation.

        Returns:
            True if the operation is allowed, False if blocked.
        """
        # Factor 1: Scope match — if rule doesn't cover this scope, allow
        op_scope = operation.get("scope", "")
        if op_scope not in [s.value for s in self.permission_scopes]:
            return True

        # Factor 2: Provider restrictions — block if provider is restricted
        provider = operation.get("provider", "")
        if provider in self.provider_restrictions:
            return False

        # Factor 3: Data classification threshold
        # A rule with CONFIDENTIAL classification blocks operations tagged
        # SENSITIVE or CONFIDENTIAL (but not PUBLIC or INTERNAL)
        op_classification = operation.get("data_classification", "")
        if op_classification:
            classification_order = {
                DataClassification.PUBLIC: 0,
                DataClassification.INTERNAL: 1,
                DataClassification.SENSITIVE: 2,
                DataClassification.CONFIDENTIAL: 3,
            }
            rule_level = classification_order.get(self.data_classification, 0)
            op_level = classification_order.get(DataClassification(op_classification), 0)
            # Block if operation's data is classified >= rule's threshold
            if op_level >= rule_level and op_level > 0:
                return False

        return True


@dataclass
class PhaseLedger:
    """Token accounting ledger for a single phase."""

    phase: str
    used_tokens: int
    budget_tokens: int
    budget_mode: BudgetMode
    status: GateStatus = GateStatus.PASSED
    message: str = ""

    @property
    def remaining(self) -> int:
        return max(self.budget_tokens - self.used_tokens, 0)

    @property
    def exceeded(self) -> bool:
        return self.used_tokens > self.budget_tokens


@dataclass
class PhaseGate:
    """Result of a single gate evaluation for a phase."""

    id: str
    phase: str
    status: GateStatus = GateStatus.PASSED
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HarnessArtifact:
    """An artifact produced during a harness run."""

    id: str
    phase: str
    path: str
    kind: str
    description: str = ""


@dataclass
class HarnessDecision:
    """A decision recorded during a harness run."""

    id: str
    phase: str
    status: str
    rationale: str
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HarnessRunResult:
    """Complete result of a harness run."""

    run_id: str
    workflow: str
    task: str
    status: GateStatus
    ledgers: list[PhaseLedger] = field(default_factory=list)
    gates: list[PhaseGate] = field(default_factory=list)
    artifacts: list[HarnessArtifact] = field(default_factory=list)
    decisions: list[HarnessDecision] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

"""Data models for the Harness system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.models.trace import RunEvent


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
    # Set on the HarnessRunResult when the apply phase ran with no edits AND
    # no productive executor was configured. Distinct from WARNING (which is
    # reserved for genuine advisories on runs that did real work) and from
    # PASSED (which would imply edits were written). Mirrors OC Flow's
    # ``needs_executor`` vocabulary so the two surfaces stay consistent.
    NOT_APPLIED = "not_applied"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}.{self.name}>"

    @property
    def is_ok(self) -> bool:
        """True if status is non-blocking (PASSED, SKIPPED, or NOT_APPLIED).

        ``NOT_APPLIED`` means no executor was configured and nothing was written
        — it is NOT a failure.  ``boundary.py`` already maps it to
        ``success=True``; ``is_ok`` must agree so ``QualityReport.exit_code``
        returns 0 and no consumer misbehaves.
        ``WARNING`` and ``FAILED`` are intentionally excluded: WARNING is an
        advisory on a run that did real work, FAILED is a hard gate failure.
        """
        return self in (GateStatus.PASSED, GateStatus.SKIPPED, GateStatus.NOT_APPLIED)


class GateSeverity(StrEnum):
    """Severity of a gate finding (PR-006, book doc 07 §9 GateResult).

    Ordered info < warning < error < critical. Independent of ``GateStatus``: a
    FAILED gate may be ``warning`` (advisory) or ``critical`` (hard block).
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}.{self.name}>"


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
    """Result of a single gate evaluation for a phase.

    PR-006 enriches the legacy gate with the book's GateResult fields
    (``severity``/``evidence_refs``/``blocking``, doc 07 §9). All three are
    defaulted so the 16 existing gate constructors (id/phase/status/message) keep
    working unchanged; ``to_gate_result()`` projects onto the book ``GateResult``.
    """

    id: str
    phase: str
    status: GateStatus = GateStatus.PASSED
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    severity: GateSeverity = GateSeverity.WARNING
    evidence_refs: list[str] = field(default_factory=list)
    blocking: bool = False

    def to_gate_result(self) -> Any:
        """Project this gate onto the book ``GateResult`` (PR-006). Imported lazily
        to avoid an import cycle (``results`` imports this module)."""
        from opencontext_core.harness.results import GateResult

        return GateResult(
            gate_id=self.id,
            status=self.status,
            severity=self.severity,
            message=self.message,
            evidence_refs=list(self.evidence_refs),
            blocking=self.blocking,
        )


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


class HarnessReport(BaseModel):
    """JSON-serializable harness report for archive gate consumption."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.harness_report.v1"
    run_id: str = ""
    change_id: str = ""
    passed: bool = False
    failures: list[str] = Field(default_factory=list)
    duration_s: float = 0.0


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
    events: list[RunEvent] = field(default_factory=list)
    # Source paths the explore pack dropped (state.context_omitted_paths). Carried
    # so the memory harvester can record them as FAILURE linked_nodes, feeding the
    # retrieval recent_failure boost on the next run.
    context_omitted_paths: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # REG-CONV: a noisy harness must be measurable. Fraction of gate findings later
    # judged false positives (0.0 default; populated by the benchmark loop in PR-017).
    false_positive_rate: float = 0.0

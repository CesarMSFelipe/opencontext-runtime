"""Data models for the Harness system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from opencontext_core.compat import StrEnum


class BudgetMode(StrEnum):
    """Token budget enforcement mode."""

    OFF = "off"
    WARN = "warn"
    STRICT = "strict"


class GateStatus(StrEnum):
    """Status of a phase gate evaluation."""

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


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
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

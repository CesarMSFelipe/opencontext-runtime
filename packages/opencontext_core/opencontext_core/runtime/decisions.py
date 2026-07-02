"""Runtime decision contracts (PR-000.1 — Decision Contract v1).

Every runtime *selection* (next node, persona, provider, …) is recorded as a
single, typed :class:`RuntimeDecision` carrying *what* was chosen and *why*. The
Runtime Brain (``brain.py``) recommends; the deterministic State Machine
(``state_machine.py``) governs — these models are advisory evidence, not control.

Backward compatibility: the PR-001 convergence seam constructed
``RuntimeDecision(kind=..., chosen=..., reason=...)`` and used the in-memory
:class:`DecisionLog` attached to a run; both keep working. PR-000.1 *extends*
the record with the design-contract fields (``selected``/``rationale`` aliases,
``confidence``, ``inputs``, ``governed_by``, ``receipt_id``, run identity) and
the ``DecisionKind`` enum, the ``SchedulingDecision``/``NextNodeDecision`` /
``SimulationReport`` scheduler contracts, and the per-run inspection helper.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC, StrEnum
from opencontext_core.runtime.ids import new_decision_id

# Internal contract version (doc 59 §Internal contract versioning). Bump on a
# breaking change; a guard test asserts this value so accidental drift is caught.
DECISION_CONTRACT_VERSION = 1

# Event family for decision-layer events (doc 59 §Event hierarchy). Decisions
# belong to the ``runtime`` family; Studio renders one lane per family.
DECISION_EVENT_FAMILY = "runtime"


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class DecisionKind(StrEnum):
    """The eight selection kinds the Runtime Brain can decide (book §11).

    ``workflow`` and ``memory_promotion`` are OC Flow runner extensions:
    workflow = which workflow was selected (oc-flow vs sdd);
    memory_promotion = the PromotionPolicyV2 verdict from consolidation.
    """

    next_node = "next_node"
    persona = "persona"
    skill_bundle = "skill_bundle"
    harnesses = "harnesses"
    context_strategy = "context_strategy"
    provider = "provider"
    execution_profile = "execution_profile"
    retry_policy = "retry_policy"
    # C16 (product-closure-r13): runner-level selections.
    workflow = "workflow"
    memory_promotion = "memory_promotion"


class RuntimeDecision(BaseModel):
    """A single runtime decision: what was chosen, the alternatives, and why.

    ``chosen``/``reason`` are the canonical storage fields (kept from the PR-001
    seam); ``selected``/``rationale`` are read-only aliases for the design
    contract. ``kind`` is a plain ``str`` so both the eight canonical
    :class:`DecisionKind` values and legacy seam labels validate.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.runtime_decision.v1"
    contract_version: int = DECISION_CONTRACT_VERSION
    decision_id: str = Field(default_factory=new_decision_id)
    kind: str
    chosen: str
    reason: str = ""
    alternatives: list[str] = Field(default_factory=list)

    # Run identity (optional — the seam ctor omits them).
    session_id: str | None = None
    run_id: str | None = None
    node_id: str | None = None

    # Adaptive-but-not-opaque evidence (book §9.8): record inputs + confidence,
    # never a persisted chain-of-thought.
    confidence: float = 0.0
    inputs: dict[str, Any] = Field(default_factory=dict)

    # Set when a higher authority overrode the recommendation (no silent
    # override — RB-008). E.g. ``"state_machine"`` or ``"policy"``.
    governed_by: str | None = None

    # Reference to the emitted ``AgenticReceipt`` (RB-010). ``rcpt_<ulid>``.
    receipt_id: str | None = None

    created_at: str = Field(default_factory=_now_iso)

    @property
    def selected(self) -> str:
        """Design-contract alias for :attr:`chosen`."""
        return self.chosen

    @property
    def rationale(self) -> str:
        """Design-contract alias for :attr:`reason`."""
        return self.reason


class DecisionLog(BaseModel):
    """An append-only, in-memory log of :class:`RuntimeDecision` entries.

    Attached to every :class:`~opencontext_core.runtime.run.RuntimeRun`. Never
    rewrites prior entries (RB-003). The durable, run-scoped Decision API sink
    lives in ``decision_log.py`` (:class:`DecisionRecorder`).
    """

    model_config = ConfigDict(extra="forbid")

    entries: list[RuntimeDecision] = Field(default_factory=list)

    def append(self, decision: RuntimeDecision) -> RuntimeDecision:
        """Append a decision and return it (never rewrites prior entries)."""
        self.entries.append(decision)
        return decision

    def for_kind(self, kind: str) -> list[RuntimeDecision]:
        """Return the entries whose ``kind`` matches (newest last)."""
        wanted = str(kind)
        return [d for d in self.entries if d.kind == wanted]

    def __len__(self) -> int:
        return len(self.entries)


class NextNodeDecision(BaseModel):
    """The Scheduler's proposed next node — advisory input to the State Machine."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.next_node_decision.v1"
    current_node: str | None = None
    proposed_node: str | None = None
    reason: str = ""
    confidence: float = 0.0


class SchedulingDecision(BaseModel):
    """A scheduling proposal: a :class:`NextNodeDecision` plus its decision record.

    The authoritative transition is produced by the PR-001 ``StateMachine``,
    never here — this is advisory only (RB-004/RB-007).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.scheduling_decision.v1"
    run_id: str
    next_node: NextNodeDecision
    decision: RuntimeDecision


class SimulationReport(BaseModel):
    """A dry-run forecast of a plan (RB-004 / Scheduler API ``simulate``).

    PR-000.1 ships a typed *seam* with a stub estimate; the real cost/confidence
    estimator lands with PR-011 (Runtime Intelligence).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.simulation_report.v1"
    run_id: str | None = None
    proposed_path: list[str] = Field(default_factory=list)
    estimated_tokens: int | None = None
    estimated_cost: float | None = None
    estimated_duration_ms: int | None = None
    estimator: str = "stub"
    notes: list[str] = Field(default_factory=list)


def summarize_decision_log(
    log: DecisionLog | list[RuntimeDecision],
) -> list[dict[str, Any]]:
    """Project a decision log to inspectable rows (RB-009).

    Returns one row per decision with ``kind``, ``selected``, ``alternatives``,
    and ``rationale`` — the shape a CLI command or MCP tool surfaces for a run.
    """
    decisions = log.entries if isinstance(log, DecisionLog) else list(log)
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        rows.append(
            {
                "decision_id": decision.decision_id,
                "kind": decision.kind,
                "selected": decision.selected,
                "alternatives": list(decision.alternatives),
                "rationale": decision.rationale,
                "confidence": decision.confidence,
                "governed_by": decision.governed_by,
                "receipt_id": decision.receipt_id,
            }
        )
    return rows

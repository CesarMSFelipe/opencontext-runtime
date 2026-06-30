"""OC Flow data models (PR-007, book doc 04 §6-§14, §22).

These are the L0 contracts OC Flow produces and consumes: the frozen
:class:`TaskContract` (the immutable plan), the evidence-driven
:class:`DiagnosisAttempt`, the zero-LLM :class:`InspectionReport`, the
:class:`EscalationReport`, and the typed :class:`ContextEnvelope` *seam* that
PR-010 will fill (today it is assembled by the existing retrieval planner).

Layering (doc 58): OC Flow is L9 but these are pure data models — they import only
pydantic + L0 ``compat``, never Runtime/registries, so the contracts stay a leaf.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from opencontext_core.compat import StrEnum

# OC Flow contract version (doc 59 — internal contract versioning). Bump on a
# breaking change to any model below; a guard test asserts the value.
OC_FLOW_CONTRACT_VERSION = 1

# Hard ceiling on diagnosis attempts regardless of profile (book §12: "Maximum
# attempts are profile-controlled" but never more than three).
MAX_DIAGNOSIS_ATTEMPTS = 3

# The exact number of hypotheses a diagnosis attempt must carry (book §12).
REQUIRED_HYPOTHESIS_COUNT = 3


class Lane(StrEnum):
    """Execution lane (FLOW-CONV §6). Maps onto a PR-000.2 execution strategy.

    A lane deterministically sets context depth, diagnosis attempt budget and
    harness strictness for a run — ``careful`` permits more than ``fast``.
    """

    FAST = "fast"
    CHEAP = "cheap"
    CAREFUL = "careful"


class NodeOutcome(StrEnum):
    """The typed outcome a node reports, driving edge resolution (book §11-§12)."""

    # local_inspection outcomes
    PASSED = "passed"
    FAILED_RECOVERABLE = "failed_recoverable"
    FAILED_BLOCKING = "failed_blocking"
    SKIPPED_WITH_REASON = "skipped_with_reason"
    # diagnose outcomes
    FIX_READY = "fix_ready"
    NEEDS_CONTEXT = "needs_context"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    POLICY_BLOCKED = "policy_blocked"
    # generic linear-node outcome
    OK = "ok"


class TaskContract(BaseModel):
    """The short, immutable plan produced by the ``plan`` node (book §9, FLOW-4).

    Frozen after creation: once ``plan`` produces it, ``mutate`` / ``local_inspection``
    / ``diagnose`` consume it but may never mutate it (structural immutability, not
    convention).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: str = Field(description="What the change covers (one focused task).")
    non_scope: list[str] = Field(default_factory=list, description="Explicitly out of scope.")
    acceptance_criteria: list[str] = Field(description="Conditions the change must satisfy.")
    constraints: list[str] = Field(default_factory=list, description="Constraints to honour.")
    changed_areas: list[str] = Field(
        default_factory=list, description="Files/symbols expected to change (blast radius)."
    )
    verification_plan: list[str] = Field(description="How the change will be verified.")
    risk_flags: list[str] = Field(default_factory=list, description="Risk markers raised at plan.")
    stop_conditions: list[str] = Field(
        default_factory=list, description="Conditions that abort the run."
    )

    @field_validator("acceptance_criteria", "verification_plan")
    @classmethod
    def _non_empty(cls, value: list[str]) -> list[str]:
        """A contract is only valid with at least one criterion and one check."""
        if not value:
            raise ValueError("must declare at least one item")
        return value


class Hypothesis(BaseModel):
    """One candidate root cause considered during diagnosis (book §12)."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(description="The hypothesised root cause.")
    evidence: str = Field(default="", description="Concrete evidence for/against it.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DiagnosisAttempt(BaseModel):
    """A single bounded, evidence-driven diagnosis attempt (book §12, FLOW-5).

    Captures the reproduction, EXACTLY three hypotheses, the selected hypothesis
    (with evidence) and the fix strategy. Persisted as ``diagnosis/attempt-NNN.json``.
    """

    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1, le=MAX_DIAGNOSIS_ATTEMPTS, description="1-based attempt number.")
    reproduction_command: str = Field(description="Command that reproduces the failure.")
    reproduction_result: str = Field(default="", description="Observed reproduction output.")
    hypotheses: list[Hypothesis] = Field(description="Exactly three candidate root causes.")
    selected_hypothesis: int = Field(description="Index into ``hypotheses`` of the chosen one.")
    fix_strategy: str = Field(description="The strategy chosen to fix the selected cause.")
    mutation_proposal: dict[str, Any] | None = Field(
        default=None, description="Optional proposed mutation for the next ``mutate``."
    )

    @field_validator("hypotheses")
    @classmethod
    def _exactly_three(cls, value: list[Hypothesis]) -> list[Hypothesis]:
        """Book §12: not one, not five — exactly three hypotheses."""
        if len(value) != REQUIRED_HYPOTHESIS_COUNT:
            raise ValueError(
                f"a diagnosis attempt requires exactly {REQUIRED_HYPOTHESIS_COUNT} "
                f"hypotheses, got {len(value)}"
            )
        return value

    @model_validator(mode="after")
    def _selected_in_range(self) -> DiagnosisAttempt:
        """The selected index must address one of the three hypotheses."""
        if not 0 <= self.selected_hypothesis < len(self.hypotheses):
            raise ValueError(
                f"selected_hypothesis {self.selected_hypothesis} out of range "
                f"[0, {len(self.hypotheses)})"
            )
        return self

    @property
    def selected(self) -> Hypothesis:
        """The chosen hypothesis."""
        return self.hypotheses[self.selected_hypothesis]


class InspectionReport(BaseModel):
    """The zero-LLM local inspection result (book §11, FLOW-8).

    ``llm_tokens`` MUST be 0 — local inspection spends no model tokens by design.
    """

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["passed", "failed_recoverable", "failed_blocking", "skipped_with_reason"]
    gate_results: list[dict[str, Any]] = Field(default_factory=list)
    failure_summary: str = Field(default="", description="Why it failed, if it did.")
    verified_by: list[str] = Field(default_factory=list, description="Commands that verified it.")
    verification_outcome: str = Field(default="not_run", description="passed|failed|not_run.")
    llm_tokens: int = Field(default=0, description="Always 0 — local inspection is LLM-free.")

    @field_validator("llm_tokens")
    @classmethod
    def _zero_tokens(cls, value: int) -> int:
        """Reject any non-zero LLM token spend for local inspection."""
        if value != 0:
            raise ValueError("local_inspection must spend 0 LLM tokens")
        return value


class EscalationReport(BaseModel):
    """A human handoff produced when the runtime cannot safely converge (book §13)."""

    model_config = ConfigDict(extra="forbid")

    blocking_error: str = Field(description="The error that blocked convergence.")
    owner_candidates: list[str] = Field(
        default_factory=list, description="Candidate owners for the blocked area."
    )
    known_blockers: list[str] = Field(default_factory=list)
    next_recommended_action: str = Field(default="", description="What a human should do next.")
    failed_strategies: list[str] = Field(
        default_factory=list, description="Strategies already ruled out (do not retry)."
    )


class ContextEnvelopeItem(BaseModel):
    """One retrieved context item inside the envelope."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Where it came from: kg|signature|test|owner|memory|file.")
    ref: str = Field(description="Symbol id / file path / memory id.")
    summary: str = Field(default="", description="Short description of the item.")
    tokens: int = Field(default=0, description="Estimated token cost of the item.")
    full_file_reason: str = Field(
        default="", description="Recorded reason if a whole file was read (book §8 rule)."
    )


class ContextEnvelope(BaseModel):
    """The minimal-sufficient context for the task (book §8, FLOW-CONV surgical).

    This is the typed *seam* PR-010 will own (the surgical ``ContextEnvelope``).
    Today it is assembled by the existing retrieval planner / KG; the shape is
    stable so the planner output can be projected into it without caller churn.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.oc_flow.context_envelope.v1"
    task: str
    items: list[ContextEnvelopeItem] = Field(default_factory=list)
    omissions: list[str] = Field(
        default_factory=list, description="Relevant context deliberately omitted (book §8)."
    )
    token_estimate: int = Field(
        default=0, description="Deterministic token estimate (PR-011 seam)."
    )
    cache_hit: bool = Field(default=False, description="True when reused from the semantic cache.")

    @property
    def has_items(self) -> bool:
        """An envelope is usable for ``plan`` only when it carries at least one item."""
        return bool(self.items)

"""Learning candidate extraction (SPEC DL-003 / DL-010).

Post-run, classify the run's evidence into typed ``LearningCandidate``s and score
``LearningOutcome``s. The proposal backend is REUSED, not re-derived:
``extract`` calls :meth:`EvolutionEngine.propose_from_run` (DL-010) and classifies
its propose-only proposals — plus harvested memory records and low-confidence
Decision Log entries — into candidates. No second propose-from-run engine is added.

Every durable text field (``summary``) is passed through the no-CoT guard
(``redact_chain_of_thought``) before it can be persisted (SPEC DL-007).
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.learning.evolution import EvolutionProposal
from opencontext_core.learning.evolution_engine import EvolutionEngine
from opencontext_core.runtime.decision_log import redact_chain_of_thought

if TYPE_CHECKING:
    from opencontext_core.learning.feedback import RuntimeFeedback
    from opencontext_core.runtime.decision_log import DecisionRecorder


class LearningCandidateKind(StrEnum):
    """How a learning candidate is classified."""

    context_weight = "context_weight"
    budget_profile = "budget_profile"
    harness_gate = "harness_gate"
    skill_candidate = "skill_candidate"
    memory_promotion = "memory_promotion"
    decision_pattern = "decision_pattern"


# EvolutionProposal.kind -> LearningCandidateKind. propose_from_run only emits the
# first four; the rest are defaulted defensively.
_PROPOSAL_KIND_MAP: dict[str, LearningCandidateKind] = {
    "context_weight": LearningCandidateKind.context_weight,
    "budget_profile": LearningCandidateKind.budget_profile,
    "harness_gate": LearningCandidateKind.harness_gate,
    "skill_candidate": LearningCandidateKind.skill_candidate,
    "memory_promotion": LearningCandidateKind.memory_promotion,
}


class LearningCandidate(BaseModel):
    """A classified, evidence-backed learning candidate (durable — no CoT)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.learning_candidate.v1"
    candidate_id: str
    run_id: str
    kind: LearningCandidateKind
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    # Links a backing EvolutionProposal (when the candidate came from the engine).
    proposal_id: str | None = None


class LearningOutcome(BaseModel):
    """The measured outcome of a learning candidate against its run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.learning_outcome.v1"
    candidate_id: str
    run_id: str
    success: bool | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


def _candidate_id(run_id: str, kind: str, key: str) -> str:
    return hashlib.sha256(f"{run_id}:{kind}:{key}".encode()).hexdigest()[:16]


def _run_id_of(run_result: Any) -> str:
    return str(getattr(run_result, "run_id", "") or "")


def _candidate_from_proposal(proposal: EvolutionProposal, run_id: str) -> LearningCandidate:
    kind = _PROPOSAL_KIND_MAP.get(proposal.kind, LearningCandidateKind.skill_candidate)
    return LearningCandidate(
        candidate_id=_candidate_id(run_id, kind.value, proposal.proposal_id),
        run_id=run_id,
        kind=kind,
        summary=redact_chain_of_thought(proposal.title),
        evidence_refs=list(proposal.evidence_refs),
        confidence=proposal.confidence,
        proposal_id=proposal.proposal_id,
    )


def _memory_candidates(harvested: list[Any], run_id: str) -> list[LearningCandidate]:
    """Project harvested memory records into memory-promotion candidates.

    Accepts ``MemoryLearningCandidate`` (PR-009 seam) or any object exposing
    ``content``/``record_id``/``id``. The loop ROUTES these to the Memory Harness
    for governed promotion; it never writes durable memory itself (SPEC DL-008).
    """
    out: list[LearningCandidate] = []
    for item in harvested:
        rec_id = str(getattr(item, "record_id", None) or getattr(item, "id", "") or "")
        content = str(getattr(item, "content", "") or "")
        out.append(
            LearningCandidate(
                candidate_id=_candidate_id(run_id, "memory_promotion", rec_id or content[:32]),
                run_id=run_id,
                kind=LearningCandidateKind.memory_promotion,
                summary=redact_chain_of_thought(content),
                evidence_refs=[f"memory:{rec_id}"] if rec_id else [],
                confidence=float(getattr(item, "confidence", 0.5) or 0.5),
            )
        )
    return out


def _decision_candidates(
    decision_log: DecisionRecorder | None, run_id: str
) -> list[LearningCandidate]:
    """Flag low-confidence Decision Log entries as decision-pattern candidates."""
    if decision_log is None:
        return []
    out: list[LearningCandidate] = []
    for entry in decision_log.entries():
        if entry.confidence >= 0.4:
            continue
        out.append(
            LearningCandidate(
                candidate_id=_candidate_id(run_id, "decision_pattern", entry.entry_id),
                run_id=run_id,
                kind=LearningCandidateKind.decision_pattern,
                summary=redact_chain_of_thought(
                    f"low-confidence {entry.decision_kind} selection: {entry.selected}"
                ),
                evidence_refs=[entry.entry_id],
                confidence=entry.confidence,
            )
        )
    return out


def extract(
    *,
    decision_log: DecisionRecorder | None = None,
    run_result: Any = None,
    feedback: list[RuntimeFeedback] | None = None,
    harvested: list[Any] | None = None,
    proposals: list[EvolutionProposal] | None = None,
) -> list[LearningCandidate]:
    """Classify the run's evidence into learning candidates (DL-003).

    The proposal backend is :meth:`EvolutionEngine.propose_from_run` (DL-010):
    when ``proposals`` is not supplied it is computed here. Candidates also come
    from harvested memory records and low-confidence Decision Log entries.
    """
    run_id = _run_id_of(run_result)
    if proposals is None:
        proposals = EvolutionEngine().propose_from_run(
            run_result=run_result,
            memories_written=harvested or None,
        )
    candidates = [_candidate_from_proposal(p, run_id) for p in proposals]
    candidates.extend(_memory_candidates(harvested or [], run_id))
    candidates.extend(_decision_candidates(decision_log, run_id))
    return candidates


def score_outcome(
    candidate: LearningCandidate,
    run_result: Any = None,
    feedback: RuntimeFeedback | None = None,
) -> LearningOutcome:
    """Produce a ``LearningOutcome`` for *candidate* against its run (DL-003)."""
    success: bool | None = None
    if run_result is not None:
        status = str(getattr(run_result, "status", "") or "").lower()
        if status:
            success = status in ("passed", "success", "ok", "completed")
    metrics: dict[str, float] = {"confidence": float(candidate.confidence)}
    if feedback is not None:
        metrics["tokens_used"] = float(feedback.tokens_used)
        metrics["context_items_omitted"] = float(feedback.context_items_omitted)
        if feedback.success is not None and success is None:
            success = feedback.success
    return LearningOutcome(
        candidate_id=candidate.candidate_id,
        run_id=candidate.run_id,
        success=success,
        metrics=metrics,
    )


__all__ = [
    "LearningCandidate",
    "LearningCandidateKind",
    "LearningOutcome",
    "extract",
    "score_outcome",
]

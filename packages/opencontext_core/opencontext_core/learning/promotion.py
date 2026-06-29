"""ImprovementProposal promotion gate (SPEC DL-005 / DL-009 / DL-011).

The honesty gate: an :class:`ImprovementProposal` (an alias of the propose-only
``EvolutionProposal`` — DL-005) is NOT promotable until it carries a
``benchmark_evidence_ref``. Improvement must be *measured*, not self-asserted
([[oc-value-eval-2026-06]]). Persistence stays the existing ``EvolutionStore``
(DL-011) — no parallel store is created here.

PR-011's benchmark gate is REUSED (not re-implemented) the same way
``EvolutionApplier`` does it: an optional, duck-typed ``benchmark_gate`` with a
``can_promote(candidate, results, ...)`` method is injected by the caller. The
learning layer never imports ``runtime_intelligence`` (doc 58 layering); when a
gate + concrete benchmark results are supplied, evaluation delegates to it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from opencontext_core.learning.evolution import EvolutionProposal, ImprovementProposal
from opencontext_core.runtime.decision_log import redact_chain_of_thought

__all__ = [
    "ImprovementProposal",
    "PromotionDecision",
    "PromotionGate",
    "harden_proposal",
]


def harden_proposal(proposal: EvolutionProposal) -> EvolutionProposal:
    """Return a copy of *proposal* with title/rationale redacted of CoT (DL-007)."""
    title = redact_chain_of_thought(proposal.title)
    rationale = redact_chain_of_thought(proposal.rationale)
    if title == proposal.title and rationale == proposal.rationale:
        return proposal
    return proposal.model_copy(update={"title": title, "rationale": rationale})


class PromotionDecision(BaseModel):
    """The gate's verdict on whether a proposal may be promoted."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.promotion_decision.v1"
    proposal_id: str
    promotable: bool
    reason: str = ""
    requires_approval: bool = True


class PromotionGate:
    """Block promotion of any proposal lacking benchmark evidence (DL-009)."""

    def __init__(self, *, require_benchmark_evidence: bool = True) -> None:
        self.require_benchmark_evidence = require_benchmark_evidence

    def evaluate(
        self,
        proposal: ImprovementProposal,
        *,
        benchmark_gate: Any = None,
        benchmark_results: list[Any] | None = None,
        candidate: Any = None,
        rollback_available: bool = True,
    ) -> PromotionDecision:
        """Return whether *proposal* may be promoted.

        Honesty gate first: an empty ``benchmark_evidence_ref`` is never
        promotable. When the caller supplies PR-011's benchmark gate plus concrete
        ``benchmark_results``, evaluation delegates to it (reuse, not re-impl).
        Eligible proposals still require approval (propose-only stays intact).
        """
        ref = (proposal.benchmark_evidence_ref or "").strip()
        if self.require_benchmark_evidence and not ref:
            return PromotionDecision(
                proposal_id=proposal.proposal_id,
                promotable=False,
                reason="missing benchmark evidence: improvement must be measured, not asserted",
                requires_approval=proposal.requires_approval,
            )

        if benchmark_gate is not None and benchmark_results is not None:
            cand = candidate or self._candidate_for(proposal)
            promotable, reason = benchmark_gate.can_promote(
                cand, benchmark_results, rollback_available=rollback_available
            )
            return PromotionDecision(
                proposal_id=proposal.proposal_id,
                promotable=bool(promotable),
                reason=str(reason),
                requires_approval=proposal.requires_approval,
            )

        return PromotionDecision(
            proposal_id=proposal.proposal_id,
            promotable=True,
            reason="ok",
            requires_approval=proposal.requires_approval,
        )

    @staticmethod
    def _candidate_for(proposal: ImprovementProposal) -> Any:
        """Build the book ``EvolutionCandidate`` shape PR-011's gate expects.

        Uses the ``models`` layer only (importable); avoids importing the
        ``runtime_intelligence`` package (doc 58 layering).
        """
        from opencontext_core.models.intelligence import EvolutionCandidate

        return EvolutionCandidate(
            candidate_id=proposal.proposal_id,
            target_type=proposal.kind,
            change_summary=proposal.title,
            rationale=proposal.rationale,
            generated_from_runs=list(proposal.evidence_refs),
            required_benchmarks=["first-run"],
            requires_approval=proposal.requires_approval,
        )

"""Runtime Optimizer interface (RI-CONV / OC-FINAL-CONVERGENCE-001 §6).

The convergence section requires a Runtime Optimizer that emits evidence-backed
optimization recommendations over cache / context / profile / routing WITHOUT
applying them automatically. PR-000.3 (the Cache/Optimization package, a sibling
change) supplies the concrete cache recommendations; this module owns the
**interface** and a propose-only default sourced from the existing
:class:`~opencontext_core.learning.evolution_engine.EvolutionEngine`.

Invariants (RI-CONV):
* Recommendations are propose-only — ``requires_approval=True``, never auto-applied
  (Runtime Intelligence recommends; Runtime governs).
* Promotion of any recommendation is benchmark-gated — it reuses
  :class:`~opencontext_core.runtime_intelligence.evolution.CandidatePromotionGate`.

Ownership note: the concrete cache optimizer lives in the sibling ``optimization/``
package (PR-000.3); this file deliberately does not touch it — it defines the port
the sibling implements and a learning-sourced default.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.learning.evolution import EvolutionProposal
from opencontext_core.learning.evolution_engine import EvolutionEngine

OptimizationTarget = Literal["cache", "context", "profile", "routing"]


class RuntimeOptimizationRecommendation(BaseModel):
    """One evidence-backed, propose-only optimization recommendation (RI-CONV)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.optimization_recommendation.v1"
    recommendation_id: str
    target: OptimizationTarget
    summary: str
    rationale: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    expected_benefit: str = ""
    # Promotion of any improvement requires passing benchmarks (benchmark-gated).
    required_benchmarks: list[str] = Field(default_factory=lambda: ["first-run"])
    # Never silently overrides the Runtime — recommend-only.
    requires_approval: bool = True


@runtime_checkable
class RuntimeOptimizer(Protocol):
    """Port: emit propose-only optimization recommendations.

    PR-000.3 (``optimization/``) supplies the concrete cache implementation; the
    intelligence layer consumes this port without depending on the sibling
    package's internals.
    """

    def recommend(self, **evidence: Any) -> list[RuntimeOptimizationRecommendation]:
        """Return evidence-backed recommendations (never applied automatically)."""
        ...


# Map a legacy evolution-proposal kind to an optimization target.
_KIND_TO_TARGET: dict[str, OptimizationTarget] = {
    "context_weight": "context",
    "budget_profile": "profile",
    "kg_refresh_policy": "context",
}


class LearningRuntimeOptimizer:
    """Default propose-only optimizer sourced from the EvolutionEngine.

    Wraps the existing propose-only evolution flow: each relevant
    :class:`EvolutionProposal` becomes a
    :class:`RuntimeOptimizationRecommendation`. No parallel optimization system is
    created; cache recommendations come from the sibling ``optimization/`` package
    via the :class:`RuntimeOptimizer` port.
    """

    def __init__(self, *, engine: EvolutionEngine | None = None) -> None:
        self._engine = engine or EvolutionEngine()

    def recommend(self, **evidence: Any) -> list[RuntimeOptimizationRecommendation]:
        proposals = self._engine.propose_from_run(
            run_result=evidence.get("run_result"),
            learned_patterns=evidence.get("learned_patterns"),
            optimized_budgets=evidence.get("optimized_budgets"),
            memories_written=evidence.get("memories_written"),
        )
        return [self._to_recommendation(p) for p in proposals if p.kind in _KIND_TO_TARGET]

    @staticmethod
    def _to_recommendation(proposal: EvolutionProposal) -> RuntimeOptimizationRecommendation:
        return RuntimeOptimizationRecommendation(
            recommendation_id=proposal.proposal_id,
            target=_KIND_TO_TARGET[proposal.kind],
            summary=proposal.title,
            rationale=proposal.rationale,
            evidence_refs=list(proposal.evidence_refs),
            requires_approval=True,
        )


__all__ = [
    "LearningRuntimeOptimizer",
    "OptimizationTarget",
    "RuntimeOptimizationRecommendation",
    "RuntimeOptimizer",
]

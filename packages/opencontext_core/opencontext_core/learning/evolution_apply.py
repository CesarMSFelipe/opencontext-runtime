"""EvolutionApplier — applies approved low-risk evolution proposals.

Only ``context_weight`` and ``budget_profile`` proposals are auto-applicable.
All other kinds require manual implementation and will return applied=False.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from opencontext_core.learning.evolution import EvolutionProposal
from opencontext_core.models.intelligence import BenchmarkResult, EvolutionCandidate


class EvolutionApplyResult(BaseModel):
    proposal_id: str
    applied: bool
    changed_files: list[str] = Field(default_factory=list)
    reason: str = ""
    rollback_ref: str | None = None


class EvolutionApplier:
    LOW_RISK_TYPES: frozenset[str] = frozenset({"context_weight", "budget_profile"})

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def apply(
        self,
        proposal: EvolutionProposal,
        *,
        approved: bool,
        promotion_gate: Any = None,
        benchmark_results: list[BenchmarkResult] | None = None,
        candidate: EvolutionCandidate | None = None,
        rollback_available: bool = True,
    ) -> EvolutionApplyResult:
        if not approved:
            return EvolutionApplyResult(
                proposal_id=proposal.proposal_id,
                applied=False,
                reason="proposal not approved",
            )

        # Book §15 benchmark-gated promotion (opt-in). Runs only when the caller
        # supplies a promotion gate + benchmark results, so default behaviour is
        # unchanged. The gate is duck-typed (injected by the upper Runtime
        # Intelligence layer) to keep the learning layer free of an upward import.
        # Evolution stays propose-only: a denied gate blocks the promotion.
        if promotion_gate is not None and benchmark_results is not None:
            cand = candidate or EvolutionCandidate(
                candidate_id=proposal.proposal_id,
                target_type=proposal.kind,
                change_summary=proposal.title,
                required_benchmarks=["first-run"],
            )
            promotable, reason = promotion_gate.can_promote(
                cand, benchmark_results, rollback_available=rollback_available
            )
            if not promotable:
                return EvolutionApplyResult(
                    proposal_id=proposal.proposal_id,
                    applied=False,
                    reason=f"promotion blocked: {reason}",
                )

        if proposal.kind not in self.LOW_RISK_TYPES:
            return EvolutionApplyResult(
                proposal_id=proposal.proposal_id,
                applied=False,
                reason=f"{proposal.kind} requires manual implementation",
            )

        if proposal.kind == "context_weight":
            return self._apply_context_weight(proposal)

        if proposal.kind == "budget_profile":
            return self._apply_budget_profile(proposal)

        return EvolutionApplyResult(
            proposal_id=proposal.proposal_id,
            applied=False,
            reason="unsupported proposal kind",
        )

    def _apply_context_weight(self, proposal: EvolutionProposal) -> EvolutionApplyResult:
        # NOTE: context_weight is not auto-applicable; OpenContext performs no automatic
        # config-file mutation. Return an honest unsupported result.
        return EvolutionApplyResult(
            proposal_id=proposal.proposal_id,
            applied=False,
            reason=(
                "context_weight is not auto-applicable: OpenContext performs no "
                "automatic config-file mutation"
            ),
        )

    def _apply_budget_profile(self, proposal: EvolutionProposal) -> EvolutionApplyResult:
        # NOTE: budget_profile is not auto-applicable; OpenContext performs no automatic
        # config-file mutation. Return an honest unsupported result.
        return EvolutionApplyResult(
            proposal_id=proposal.proposal_id,
            applied=False,
            reason=(
                "budget_profile is not auto-applicable: OpenContext performs no "
                "automatic config-file mutation"
            ),
        )

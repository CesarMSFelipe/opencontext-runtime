"""EvolutionApplier — applies approved low-risk evolution proposals.

Only ``context_weight`` and ``budget_profile`` proposals are auto-applicable.
All other kinds require manual implementation and will return applied=False.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from opencontext_core.learning.evolution import EvolutionProposal


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

    def apply(self, proposal: EvolutionProposal, *, approved: bool) -> EvolutionApplyResult:
        if not approved:
            return EvolutionApplyResult(
                proposal_id=proposal.proposal_id,
                applied=False,
                reason="proposal not approved",
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
        # NOTE: context_weight proposals adjust weight config in opencontext.yaml
        # Stub: mark applied=False until config schema exposes context weights
        return EvolutionApplyResult(
            proposal_id=proposal.proposal_id,
            applied=False,
            reason="context_weight apply not yet wired to config file",
        )

    def _apply_budget_profile(self, proposal: EvolutionProposal) -> EvolutionApplyResult:
        # NOTE: budget_profile proposals adjust budget thresholds in opencontext.yaml
        # Stub: mark applied=False until config schema exposes budget profiles
        return EvolutionApplyResult(
            proposal_id=proposal.proposal_id,
            applied=False,
            reason="budget_profile apply not yet wired to config file",
        )

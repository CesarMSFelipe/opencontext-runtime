"""Evolution proposal model for the OpenContext learning layer.

``EvolutionProposal`` is the single output type of ``EvolutionEngine``.  The
engine is propose-only: it never mutates configuration, gates, or security
settings.  Every proposal requires explicit human action to take effect.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvolutionKind = Literal[
    "context_weight",
    "budget_profile",
    "harness_gate",
    "skill_candidate",
    "memory_promotion",
    "kg_refresh_policy",
    "test_policy",
]

EvolutionStatus = Literal["proposed", "approved", "applied", "rejected"]


class EvolutionProposal(BaseModel):
    """A single propose-only evolution signal.

    Every field has a sensible default except ``proposal_id``, ``kind``,
    ``title``, and ``rationale``, which must be supplied by the engine.

    IMPORTANT: ``auto_applicable=True`` MUST NOT be set for proposals whose
    ``kind`` is ``"harness_gate"`` — the engine enforces this constraint.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.evolution_proposal.v1"
    proposal_id: str
    kind: EvolutionKind
    status: EvolutionStatus = "proposed"
    title: str
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    impact: Literal["low", "medium", "high"] = "medium"
    risk: Literal["low", "medium", "high"] = "low"
    payload: dict = Field(default_factory=dict)
    auto_applicable: bool = False
    requires_approval: bool = True


__all__ = ["EvolutionKind", "EvolutionProposal", "EvolutionStatus"]

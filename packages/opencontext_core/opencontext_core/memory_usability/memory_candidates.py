"""Memory candidate models used by harvesting and novelty checks."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.models.context import DataClassification
from opencontext_core.models.evidence import EvidenceRef


class MemoryKind(StrEnum):
    """Kinds of memory that can be stored in the context repository."""

    FACT = "fact"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    ERROR = "error"
    VALIDATION = "validation"
    SUMMARY = "summary"


class MemoryCandidate(BaseModel):
    """Potential long-term memory extracted from a trace or user-approved source."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(description="Redacted memory candidate content.")
    source: str = Field(description="Trace id, file path, or source reference.")
    kind: MemoryKind = Field(description="Candidate memory kind.")
    novelty_score: float = Field(ge=0.0, le=1.0, description="Estimated novelty.")
    reuse_likelihood: float = Field(ge=0.0, le=1.0, description="Likelihood of future reuse.")
    classification: DataClassification = Field(description="Candidate data classification.")
    token_cost: int = Field(ge=0, description="Estimated token cost.")
    source_trust: float = Field(default=0.5, ge=0.0, le=1.0, description="Source trust score.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Traceable scoring data.")
    # --- Book OC-MEMORY-001 §6 promotion provenance (PR-009, all defaulted) -----
    proposed_by: str = Field(
        default="", description="Persona/skill/harness that proposed this candidate."
    )
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list,
        description="Evidence backing the candidate; promotion rejects empty evidence.",
    )
    expected_reuse: str = Field(
        default="", description="Free-text statement of how this memory is expected to be reused."
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Proposer confidence in the candidate."
    )

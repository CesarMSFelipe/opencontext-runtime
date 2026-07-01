"""Memory v2 Pydantic models (PR-009).

Self-contained, provider-neutral data types for the v2 harness. The legacy
``models.memory`` / ``models.agent_memory`` types stay unchanged so the v1
store keeps validating; v2 code uses these explicitly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum


class MemoryKindV2(StrEnum):
    """Six-value v2 content intent (PR-009)."""

    DECISION = "decision"
    FACT = "fact"
    CONSTRAINT = "constraint"
    ERROR = "error"
    VALIDATION = "validation"
    SUMMARY = "summary"


class MemoryStatusV2(StrEnum):
    """Belief-validity axis for v2 records."""

    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class MemoryRecordV2(BaseModel):
    """A typed v2 memory record.

    Mirrors the v1 book surface (id, kind, topic_key, content, evidence_refs,
    source_refs, confidence, status) so the v2 harness can promote candidates
    into records without leaking the v1 schema's extra fields.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable memory id, e.g. mem_<ulid>.")
    kind: MemoryKindV2 = Field(description="Content intent of this record.")
    topic_key: str = Field(
        description="Hierarchical dedup handle like 'architecture/auth-model'."
    )
    content: str = Field(description="The memory payload (prose or structured).")
    evidence_refs: list[str] = Field(
        default_factory=list, description="Supporting evidence refs (file:line, run ids)."
    )
    source_refs: list[str] = Field(
        default_factory=list, description="Provenance traces that produced the record."
    )
    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Proposer confidence in [0, 1]."
    )
    status: MemoryStatusV2 = Field(
        default=MemoryStatusV2.ACTIVE, description="Belief-validity status."
    )
    quality_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Composite quality in [0, 1]."
    )
    created_at: datetime = Field(description="Creation timestamp (UTC).")
    updated_at: datetime = Field(description="Last update timestamp (UTC).")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Free-form metadata (e.g. layer override)."
    )


class MemoryCandidateV2(BaseModel):
    """A pre-promotion proposal destined for the harness.

    ``topic_key`` is required: without it the harness cannot dedupe and the
    conflict step becomes ambiguous.
    """

    model_config = ConfigDict(extra="forbid")

    content: str = Field(description="Redacted candidate content.")
    kind: MemoryKindV2 = Field(description="Inferred content intent.")
    topic_key: str = Field(
        min_length=1, description="Hierarchical dedup handle (required)."
    )
    evidence_refs: list[str] = Field(
        default_factory=list, description="Supporting evidence refs."
    )
    source_refs: list[str] = Field(
        default_factory=list, description="Provenance traces that produced the candidate."
    )
    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Proposer confidence in [0, 1]."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Free-form scoring data."
    )


class MemoryReceiptV2(BaseModel):
    """Receipt returned by the v2 harness on every durable write."""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(description="Id of the affected record (mem_<ulid>).")
    action: Literal["create", "update", "supersede", "reject"] = Field(
        description="Outcome of the write lifecycle."
    )
    reason: str = Field(default="", description="Stable reason code for the action.")
    evidence_refs: list[str] = Field(
        default_factory=list, description="Evidence backing the promoted record."
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(tz=UTC).isoformat(),
        description="Receipt creation timestamp (ISO 8601).",
    )


__all__ = [
    "MemoryCandidateV2",
    "MemoryKindV2",
    "MemoryReceiptV2",
    "MemoryRecordV2",
    "MemoryStatusV2",
]

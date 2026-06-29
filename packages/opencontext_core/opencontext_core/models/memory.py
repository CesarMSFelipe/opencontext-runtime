"""Memory models for future local and external memory stores."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum
from opencontext_core.models.context import DataClassification
from opencontext_core.models.evidence import EvidenceRef
from opencontext_core.models.project import ProjectManifest


def _new_receipt_id() -> str:
    """Mint a ``rcpt_<ulid>`` id. Imported lazily: ``models.memory`` is in the eager
    config-bootstrap chain, and a top-level ``runtime`` import would cycle."""
    from opencontext_core.runtime.ids import new_id

    return new_id("rcpt")


class MemoryType(StrEnum):
    """Supported memory record categories."""

    PROJECT = "project"
    FILE = "file"
    SYMBOL = "symbol"
    STRUCTURED_FACT = "structured_fact"
    DECISION = "decision"
    OBSERVATION = "observation"
    PREFERENCE = "preference"
    MILESTONE = "milestone"
    DISCOVERY = "discovery"
    ADVICE = "advice"


class MemoryItem(BaseModel):
    """A typed memory record that can be persisted or retrieved.

    Based on a hierarchical drawer structure, with support for
    hierarchical organization (wing/room) and priority-based
    retrieval.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable memory identifier.")
    memory_type: MemoryType = Field(description="Memory category.")
    content: str = Field(description="Memory payload (verbatim).")
    source: str = Field(description="Origin of the memory record.")
    created_at: datetime = Field(description="Creation timestamp.")
    classification: DataClassification = Field(
        default=DataClassification.INTERNAL,
        description="Data classification for security policy.",
    )
    priority: int = Field(
        default=1,
        description="Priority 0 (highest) to 3 (lowest).",
        ge=0,
        le=3,
    )
    trusted: bool = Field(
        default=False,
        description="Whether this memory is from a trusted source.",
    )
    redacted: bool = Field(
        default=False,
        description="Whether content has been redacted.",
    )
    tokens: int | None = Field(
        default=None,
        description="Cached token count for this item.",
        ge=0,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional memory metadata.",
    )


class MemoryQuery(BaseModel):
    """Task-aware memory retrieval request (book OC-MEMORY-001 §11).

    Drives budgeted, ordered retrieval: the planner honors ``max_records`` /
    ``max_tokens`` and the documented retrieval order (exact-tags → procedural →
    failure → semantic → episodic).
    """

    model_config = ConfigDict(extra="forbid")

    task: str = Field(description="The task text retrieval is serving.")
    workflow: str = Field(default="", description="Active workflow id (e.g. 'oc-flow').")
    node: str = Field(default="", description="Active node id (e.g. 'gather_context').")
    tags: list[str] = Field(default_factory=list, description="Exact tags to prioritize.")
    max_records: int = Field(default=8, ge=0, description="Hard cap on returned records.")
    max_tokens: int = Field(default=2000, ge=0, description="Hard cap on returned memory tokens.")
    min_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum record confidence to include."
    )


class MemoryConflict(BaseModel):
    """Typed conflict report (book OC-MEMORY-001 §13).

    Replaces the bare ``list[str]`` of contradicted ids with a structured report
    naming the existing record, summarizing the candidate, and stating the reason
    and a recommended resolution.
    """

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(description="Id of the existing record in conflict.")
    candidate_summary: str = Field(
        default="", description="Short summary of the conflicting incoming content."
    )
    reason: str = Field(description="Stable reason code for the conflict.")
    resolution: Literal["mark_stale", "supersede", "surface_uncertainty", "none"] = Field(
        default="surface_uncertainty",
        description="Recommended resolution for this conflict.",
    )


class MemoryReceipt(BaseModel):
    """Receipt emitted on every durable memory write (book OC-MEMORY-001 §25)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.memory_receipt.v1"
    receipt_id: str = Field(default_factory=_new_receipt_id)
    memory_id: str = Field(description="Id of the affected memory record (mem_<ulid>).")
    action: Literal["create", "update", "supersede", "reject"] = Field(
        description="Outcome of the write lifecycle."
    )
    reason: str = Field(default="", description="Stable reason code for the action.")
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list, description="Evidence backing the promoted record."
    )
    created_at: str = Field(default_factory=lambda: datetime.now(tz=UTC).isoformat())


class ProjectMemorySnapshot(BaseModel):
    """A project memory snapshot combining manifest, facts, and decisions."""

    model_config = ConfigDict(extra="forbid")

    manifest: ProjectManifest = Field(description="Indexed project manifest.")
    facts: list[MemoryItem] = Field(default_factory=list, description="Structured facts.")
    decisions: list[MemoryItem] = Field(default_factory=list, description="Decision memories.")
    observations: list[MemoryItem] = Field(
        default_factory=list, description="Session observations."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional snapshot metadata.",
    )

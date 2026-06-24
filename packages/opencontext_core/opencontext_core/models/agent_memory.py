"""Agent memory layer models for OpenContext Runtime v2."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from opencontext_core.compat import StrEnum
from opencontext_core.models.evidence import EvidenceRef


class MemoryLayer(StrEnum):
    """The five explicit memory layers used by the OpenContext agent memory system."""

    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    WORKING = "working"
    FAILURE = "failure"


class DecayPolicy(BaseModel):
    """Policy controlling how a memory record ages over time."""

    enabled: bool = Field(description="Whether decay is active for this record.")
    half_life_days: int = Field(default=90, description="Half-life in days when decay is enabled.")


class MemoryRecord(BaseModel):
    """A typed, versioned record in the agent memory graph."""

    id: str = Field(description="Stable unique identifier for this record.")
    layer: MemoryLayer = Field(description="Which memory layer this record belongs to.")
    key: str = Field(description="Namespaced key, e.g. 'auth:login_failure'.")
    content: str = Field(description="The memory payload.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in [0, 1].")
    source_refs: list[EvidenceRef] = Field(
        default_factory=list, description="Supporting evidence references."
    )
    decay_policy: DecayPolicy = Field(description="Decay configuration for this record.")
    tags: list[str] = Field(default_factory=list, description="Free-form tags.")
    linked_nodes: list[str] = Field(
        default_factory=list, description="Graph node IDs this record is linked to."
    )
    created_at: datetime = Field(description="Creation timestamp (UTC).")
    updated_at: datetime = Field(description="Last update timestamp (UTC).")
    supersedes: list[str] = Field(
        default_factory=list, description="IDs of records this one supersedes."
    )
    contradicted_by: list[str] = Field(
        default_factory=list, description="IDs of records that contradict this one."
    )
    valid_from: datetime | None = Field(
        default=None,
        description="Belief-validity start (UTC). Defaults to created_at when unset.",
    )
    invalid_at: datetime | None = Field(
        default=None,
        description="When this belief stopped being valid (UTC). None means still valid.",
    )
    superseded_by: str | None = Field(
        default=None, description="ID of the record that replaced this one, if any."
    )
    topic_key: str | None = Field(
        default=None,
        description="Hierarchical dedup handle like 'architecture/auth-model'. "
        "When set, store_by_topic_key() upserts in-place instead of creating duplicates.",
    )
    revision_count: int = Field(
        default=0,
        description="How many times this topic has been updated. Incremented on each upsert.",
    )
    run_id: str | None = Field(
        default=None,
        description="Run that produced this record (provenance link to a RunEnvelope/receipt).",
    )
    provenance: str | None = Field(
        default=None,
        description="Origin channel: 'agent', 'harvest', 'manual', or 'import'.",
    )

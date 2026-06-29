"""Agent memory layer models for OpenContext Runtime v2."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from opencontext_core.compat import StrEnum
from opencontext_core.models.evidence import EvidenceRef


class MemoryLayer(StrEnum):
    """The memory layers used by the OpenContext agent memory system.

    Book OC-MEMORY-001 §5 six-type taxonomy: ``episodic``, ``semantic``,
    ``procedural``, ``project``, ``failure`` (== book ``failure_pattern``) and
    ``harness_experience``. ``working`` is retained as the short-lived scratch
    layer. ``PROJECT``/``HARNESS_EXPERIENCE`` are PR-009 additions; both route to
    the local store (see ``memory/composite.py``).
    """

    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    WORKING = "working"
    FAILURE = "failure"
    PROJECT = "project"
    HARNESS_EXPERIENCE = "harness_experience"


class MemoryLifecycle(StrEnum):
    """Lifecycle state for a MemoryRecord — tracks progression from candidate to expiry."""

    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class MemoryStatus(StrEnum):
    """Book OC-MEMORY-001 §6 belief-validity axis (distinct from ``MemoryLifecycle``).

    ``lifecycle`` tracks candidate→active→superseded→expired wiring; ``status`` is
    the belief-validity of the record's content: still trusted (``active``),
    aged/contradicted but not replaced (``stale``), replaced (``superseded``), or
    refused by the promotion gate (``rejected``).
    """

    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class DecayPolicy(BaseModel):
    """Policy controlling how a memory record ages over time."""

    enabled: bool = Field(description="Whether decay is active for this record.")
    half_life_days: int = Field(default=90, description="Half-life in days when decay is enabled.")


class MemoryRecord(BaseModel):
    """A typed, versioned record in the agent memory graph.

    PR-009 adds the book OC-MEMORY-001 §6 schema fields (``schema_version``,
    ``scope``, ``structured``, ``status``, ``source_session_id``, ``last_seen_at``,
    ``quality_score``). All are defaulted so every pre-v2 constructor and serialized
    record keeps validating unchanged.
    """

    schema_version: str = Field(
        default="opencontext.memory.v1",
        description="Book schema version for this record (OC-MEMORY-001 §6).",
    )
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
    lifecycle: MemoryLifecycle = Field(
        default=MemoryLifecycle.CANDIDATE,
        description="Lifecycle state of this record.",
    )
    scope: Literal["project", "repo", "workspace", "team", "user"] = Field(
        default="project",
        description="Ownership scope of this belief (OC-MEMORY-001 §6).",
    )
    structured: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional machine-readable payload alongside the prose content.",
    )
    status: MemoryStatus = Field(
        default=MemoryStatus.ACTIVE,
        description="Belief-validity status (active/stale/superseded/rejected).",
    )
    source_session_id: str | None = Field(
        default=None,
        description="Session that produced this record (sess_<ulid>), if known.",
    )
    last_seen_at: datetime | None = Field(
        default=None,
        description="When this belief was last re-observed/re-read (UTC).",
    )
    quality_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Composite quality (evidence + reuse + freshness + confidence). "
        "Computed by memory.consolidation.memory_quality_score; 0.0 until set.",
    )


def migrate_legacy_record(payload: dict[str, Any]) -> MemoryRecord:
    """Load a serialized (possibly pre-v2) record, backfilling the book fields.

    Pre-v2 payloads lack ``schema_version``/``scope``/``status``/``structured`` etc.;
    pydantic supplies the defaults, and this helper stamps ``schema_version`` so a
    re-serialized record carries the current contract version. Idempotent: a v2
    payload round-trips unchanged.
    """
    data = dict(payload)
    data.setdefault("schema_version", "opencontext.memory.v1")
    return MemoryRecord.model_validate(data)

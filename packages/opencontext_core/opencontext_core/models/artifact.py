"""Durable artifact models + the artifact-kind registry (PR-002, L0).

Pure data, no behaviour. Defines the 17 required artifact kinds (doc 24 §16)
plus the convergence kinds (``decision-log``/``program-plan``, AR-CONV) and the
``rollback-report`` kind (doc 24 §13), the :class:`ArtifactWriteRequest` accepted
by :class:`~opencontext_core.harness.artifact_store.ArtifactStore`, the artifact
``source`` classification + cache provenance, and the :class:`Checkpoint` model
(schema ``opencontext.checkpoint.v1``) recorded by ``CheckpointManager``.

Layering (doc 58): this is an L0 model module — it imports only stdlib + pydantic.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# -- Artifact kind registry (doc 24 §16) ------------------------------------

# The 17 *required* artifact kinds the runtime must recognise (doc 24 §16).
_REQUIRED_ARTIFACT_KINDS: frozenset[str] = frozenset(
    {
        "context-envelope",
        "task-contract",
        "proposal",
        "spec",
        "design",
        "tasks",
        "mutation",
        "patch",
        "inspection-report",
        "diagnosis-attempt",
        "review-report",
        "escalation-report",
        "memory-delta",
        "graph-delta",
        "cost-report",
        "confidence-report",
        "summary",
    }
)

# Convergence kinds (OC-FINAL-CONVERGENCE-001 §6): the PR-000.1 Decision Log and
# the PR-000 ProgramPlan persist as first-class artifacts.
_CONVERGENCE_ARTIFACT_KINDS: frozenset[str] = frozenset({"decision-log", "program-plan"})

# Rollback produces a rollback-report artifact (doc 24 §13). §16 lists the
# *required* minimum; the registry is a superset, so this is an extra valid kind.
_EXTRA_ARTIFACT_KINDS: frozenset[str] = frozenset({"rollback-report"})

ARTIFACT_KINDS: frozenset[str] = (
    _REQUIRED_ARTIFACT_KINDS | _CONVERGENCE_ARTIFACT_KINDS | _EXTRA_ARTIFACT_KINDS
)

# Where an artifact's content came from (AR-CONV source classification).
ArtifactSource = Literal["generated", "inferred", "user-provided"]


class CacheMetadata(BaseModel):
    """Cache provenance for an artifact materialised from the semantic cache.

    Links an artifact to the cache entry it came from (PR-000.3) so a
    cached-vs-recomputed artifact is distinguishable on inspection (AR-CONV).
    """

    model_config = ConfigDict(extra="forbid")

    cache_key: str = Field(description="Originating cache key (cache_<hash>).")
    hit: bool = Field(description="True when the artifact was served from cache.")


class ArtifactWriteRequest(BaseModel):
    """Request to register one artifact in the durable store (doc 24 §6).

    ``kind`` MUST be one of :data:`ARTIFACT_KINDS`; ``content`` is the raw bytes
    or text to persist. ``source`` classifies provenance and ``cache_metadata``
    optionally records the cache entry the artifact came from.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    workflow_id: str | None = None
    node_id: str | None = None
    kind: str
    content: bytes | str
    media_type: str = "application/octet-stream"
    produced_by: str = "runtime"
    source: ArtifactSource = "generated"
    cache_metadata: CacheMetadata | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    required: bool = Field(
        default=False,
        description="If True, a missing/corrupt target fails resume (RES-02).",
    )

    @field_validator("kind")
    @classmethod
    def _kind_known(cls, value: str) -> str:
        if value not in ARTIFACT_KINDS:
            raise ValueError(
                f"unknown artifact kind {value!r}; must be one of {sorted(ARTIFACT_KINDS)}"
            )
        return value


class Checkpoint(BaseModel):
    """Per-mutation file snapshot record (doc 24 §12, schema checkpoint.v1).

    Records, per captured file, the content checksum of its *pre-apply* bytes and
    the snapshot path the bytes were copied to, so the snapshot can be audited and
    linked into the run manifest. The reversible snapshot/restore engine itself is
    :class:`opencontext_core.harness.checkpoint.Checkpoint` (kept distinct).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.checkpoint.v1"
    checkpoint_id: str
    session_id: str = ""
    run_id: str = ""
    files: list[str] = Field(default_factory=list)
    checksums: dict[str, str] = Field(default_factory=dict)
    snapshot_paths: dict[str, str] = Field(default_factory=dict)
    created_at: str


__all__ = [
    "ARTIFACT_KINDS",
    "ArtifactSource",
    "ArtifactWriteRequest",
    "CacheMetadata",
    "Checkpoint",
]

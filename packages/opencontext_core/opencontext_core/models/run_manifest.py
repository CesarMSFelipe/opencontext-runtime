"""Run manifest + evidence-ref models (PR-002, L0).

The per-run immutable index (doc 24 §9): a :class:`RunManifest` lists the
:class:`ArtifactRef`s, :class:`ReceiptRef`s and :class:`CheckpointRef`s a run
produced plus its events path. The book full-provenance :class:`ArtifactRef`
(doc 24 §4) lives here, deliberately kept distinct from the two existing
``ArtifactRef`` types (``models/run_envelope.py``, ``context/artifact_ref.py``)
so PR-001 / oc_new callers are untouched (design Decisions).

Layering (doc 58): L0 — imports only stdlib, pydantic, and the sibling L0
``models.artifact`` (source/cache provenance types).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import UTC
from opencontext_core.models.artifact import ArtifactSource, CacheMetadata


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class ArtifactRef(BaseModel):
    """Full-provenance reference to a stored artifact (doc 24 §4, schema artifact.v1).

    Carries the run/session/workflow/node lineage, ``kind``, content ``checksum``
    and a mandatory ``source`` classification (AR-CONV). ``required`` flags an
    artifact whose absence/corruption must fail a resume (ART-01/RES-02);
    ``cache_metadata`` records cache provenance when the artifact was served from
    the semantic cache.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.artifact.v1"
    artifact_id: str
    session_id: str = ""
    run_id: str
    workflow_id: str | None = None
    node_id: str | None = None
    kind: str
    path: str
    media_type: str = "application/octet-stream"
    produced_by: str = "runtime"
    checksum: str | None = None
    source: ArtifactSource = "generated"
    required: bool = False
    cache_metadata: CacheMetadata | None = None
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReceiptRef(BaseModel):
    """Pointer to a stored receipt by id + path (+ optional checksum/kind)."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    path: str
    kind: str | None = None
    checksum: str | None = None


class CheckpointRef(BaseModel):
    """Pointer to a stored checkpoint record by id + path (+ optional checksum)."""

    model_config = ConfigDict(extra="forbid")

    checkpoint_id: str
    path: str
    checksum: str | None = None


class RunManifest(BaseModel):
    """Immutable per-run evidence index (doc 24 §9, schema run_manifest.v1)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.run_manifest.v1"
    session_id: str = ""
    run_id: str
    workflow_id: str = ""
    status: str = "unknown"
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    receipts: list[ReceiptRef] = Field(default_factory=list)
    checkpoints: list[CheckpointRef] = Field(default_factory=list)
    events_path: str = ""
    summary_path: str | None = None
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


__all__ = [
    "ArtifactRef",
    "CheckpointRef",
    "ReceiptRef",
    "RunManifest",
]

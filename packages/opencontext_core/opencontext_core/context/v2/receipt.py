"""Context v2 receipt — ``ContextReceipt`` envelope-of-evidence (CONV2 #10 + A5).

The receipt proves what evidence a single node execution consumed. Commit-019
extends the v1 shape (7 fields) to the deep-evidence shape: 13 required fields
plus a per-read justification for any full-file read issued by the engine.
Legacy receipts (without ``full_file_reads``) still load because the field
has a default of ``[]`` and every commit-019 field is forward-compatible.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRef(BaseModel):
    """Pointer to a piece of evidence (file / symbol / memory id)."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # file | symbol | memory | doc
    id: str
    tokens: int = 0


class FullFileReadJustification(BaseModel):
    """Per-read justification emitted whenever the engine issues a FULL_FILE read."""

    model_config = ConfigDict(extra="forbid")

    path: str
    reason: str
    byte_count: int
    requested_by: str  # node id


class ContextReceipt(BaseModel):
    """The persisted proof-of-context for a single node execution (13 fields, A5)."""

    model_config = ConfigDict(extra="forbid")

    # --- 13 required fields (Amendment A5) ---------------------------------
    schema_version: str = "opencontext.context_receipt.v1"
    receipt_id: str
    request_id: str
    workflow: str
    node: str
    task: str
    decision_dependency: str = ""
    envelope_hash: str
    ranking_hash: str
    budget_hash: str
    included_refs: list[EvidenceRef] = Field(default_factory=list)
    omitted_refs: list[EvidenceRef] = Field(default_factory=list)
    used_tokens: int = 0
    available_tokens: int = 0
    confidence: float = Field(ge=0.0, le=1.0)
    full_file_reads: list[FullFileReadJustification] = Field(default_factory=list)
    created_at: datetime | None = None


__all__ = ["ContextReceipt", "EvidenceRef", "FullFileReadJustification"]
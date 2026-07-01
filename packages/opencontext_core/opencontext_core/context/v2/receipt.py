"""Context v2 receipt — ``ContextReceipt`` envelope-of-evidence (CONV2 #10).

Commit-010 ships the initial 14-field schema (confidence, hashes, refs). The
five additive fields required by Amendment A5 (``decision_dependency``,
``schema_version``, ``full_file_reads``, ``created_at`` and the documented
`schema_version`) land in commit-019 — the field set is forward-compatible
because every commit-019 field has a default.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRef(BaseModel):
    """Pointer to a piece of evidence (file / symbol / memory id)."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # file | symbol | memory | doc
    id: str
    tokens: int = 0


class ContextReceipt(BaseModel):
    """The persisted proof-of-context for a single node execution."""

    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    request_id: str
    workflow: str
    node: str
    task: str
    envelope_hash: str
    ranking_hash: str
    budget_hash: str
    included_refs: list[EvidenceRef] = Field(default_factory=list)
    omitted_refs: list[EvidenceRef] = Field(default_factory=list)
    used_tokens: int = 0
    available_tokens: int = 0
    confidence: float = Field(ge=0.0, le=1.0)

    # Forward-compat fields (populated in commit-019; defaults keep legacy loads valid).
    schema_version: str = "opencontext.context_receipt.v1"
    decision_dependency: str = ""
    full_file_reads: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = ""


__all__ = ["ContextReceipt", "EvidenceRef"]
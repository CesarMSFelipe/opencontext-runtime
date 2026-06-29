"""Durable receipt models + the receipt-kind registry (PR-002, L0).

Defines the book :class:`Receipt` (doc 24 §5), :class:`ApplyReceipt` (§11) and
:class:`RollbackReceipt` (§13), plus the 12 required receipt kinds (§17). These
are *new* models living alongside the hash/budget-shaped
``operating_model.team.RunReceipt`` (v2) — that one is not edited (design
decision: different concern).

Layering (doc 58): L0 model module — stdlib + pydantic only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from opencontext_core.compat import UTC
from opencontext_core.runtime.ids import new_receipt_id

# -- Receipt kind registry (doc 24 §17) -------------------------------------

RECEIPT_KINDS: frozenset[str] = frozenset(
    {
        "workflow-selection",
        "context-retrieval",
        "policy-decision",
        "provider-call",
        "mutation",
        "inspection",
        "diagnosis",
        "escalation",
        "memory-write",
        "kg-update",
        "consolidation",
        "benchmark",
    }
)


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class Receipt(BaseModel):
    """Proof of one decision or action (doc 24 §5, schema receipt.v1).

    ``kind`` MUST be one of :data:`RECEIPT_KINDS`. Receipts are immutable once
    written (doc 24 §15): a later receipt may supersede a decision, but the
    original line is never rewritten (the append-only
    :class:`~opencontext_core.harness.receipt_store.ReceiptStore` enforces this).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.receipt.v1"
    receipt_id: str = Field(default_factory=new_receipt_id)
    session_id: str = ""
    run_id: str | None = None
    workflow_id: str | None = None
    node_id: str | None = None
    kind: str
    action: str
    reason: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    cost: dict[str, Any] = Field(default_factory=dict)
    policy_decision_id: str | None = None
    created_at: str = Field(default_factory=_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _kind_known(cls, value: str) -> str:
        if value not in RECEIPT_KINDS:
            raise ValueError(
                f"unknown receipt kind {value!r}; must be one of {sorted(RECEIPT_KINDS)}"
            )
        return value


class ApplyReceipt(BaseModel):
    """Per-file mutation record with before/after checksums (doc 24 §11).

    Every applied file mutation produces one ``ApplyReceipt`` so a change is
    audit-replayable: ``changed`` distinguishes a real edit from a no-op write,
    and ``checksum_before``/``checksum_after`` bracket the file content.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.apply_receipt.v1"
    receipt_id: str = Field(default_factory=new_receipt_id)
    path: str
    operation: str
    changed: bool
    checksum_before: str | None = None
    checksum_after: str | None = None
    diff_path: str | None = None
    reason: str = ""
    requirement_refs: list[str] = Field(default_factory=list)
    policy_decision_id: str | None = None
    created_at: str = Field(default_factory=_now_iso)


class RollbackReceipt(BaseModel):
    """Proof that a mutation was rolled back to a checkpoint (doc 24 §13)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.rollback_receipt.v1"
    receipt_id: str = Field(default_factory=new_receipt_id)
    run_id: str | None = None
    session_id: str = ""
    checkpoint_id: str
    restored_files: list[str] = Field(default_factory=list)
    reason: str = ""
    report_artifact_id: str | None = None
    created_at: str = Field(default_factory=_now_iso)


class PhaseReceipt(BaseModel):
    """Per-SDD-phase decision receipt (spec PR-004 REQ-06 + SDD-CONV).

    One uniform receipt per executed SDD phase, recording the phase id, its
    final status, the artifacts it produced, a gate digest (gate id -> status),
    the decisions that drove it and its trace id. Written append-only through the
    :class:`~opencontext_core.harness.receipt_store.ReceiptStore` alongside the
    book :class:`Receipt`/:class:`ApplyReceipt`/:class:`RollbackReceipt`. It is a
    *distinct* schema (``opencontext.phase_receipt.v1``) with no ``kind`` field,
    so the closed 12-kind :data:`RECEIPT_KINDS` registry (doc 24 §17) is
    unaffected — a phase receipt is a workflow-level audit record, not one of the
    twelve harness/decision receipt kinds.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.phase_receipt.v1"
    receipt_id: str = Field(default_factory=new_receipt_id)
    run_id: str | None = None
    session_id: str = ""
    workflow_id: str | None = None
    phase: str
    status: str
    artifact_refs: list[str] = Field(default_factory=list)
    gate_digest: dict[str, str] = Field(default_factory=dict)
    required_harnesses: list[str] = Field(default_factory=list)
    decision_refs: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    created_at: str = Field(default_factory=_now_iso)


__all__ = [
    "RECEIPT_KINDS",
    "ApplyReceipt",
    "PhaseReceipt",
    "Receipt",
    "RollbackReceipt",
]

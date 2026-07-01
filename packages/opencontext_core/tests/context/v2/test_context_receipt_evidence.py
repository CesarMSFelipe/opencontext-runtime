"""Tests for context.v2.receipt — Amendment A5: 13-field ContextReceipt + full_file_reads.

Commit-019 extends the v1 receipt (7 fields) to the deep-evidence shape: 13
required fields, plus a per-read justification for any full-file read issued
by the engine. Legacy receipts (without ``full_file_reads``) still load
because the field has a default of ``[]``.
"""

from __future__ import annotations

from typing import get_type_hints

import pytest
from pydantic import ValidationError

from opencontext_core.context.v2.engine import ContextEngine
from opencontext_core.context.v2.receipt import (
    ContextReceipt,
    FullFileReadJustification,
)

REQUIRED_FIELDS = (
    "schema_version",
    "receipt_id",
    "request_id",
    "workflow",
    "node",
    "task",
    "decision_dependency",
    "envelope_hash",
    "ranking_hash",
    "budget_hash",
    "included_refs",
    "omitted_refs",
    "used_tokens",
    "available_tokens",
    "confidence",
    "full_file_reads",
    "created_at",
)


def test_context_receipt_has_13_required_fields() -> None:
    """Amendment A5: ContextReceipt exposes all 13 required fields by name."""
    hints = get_type_hints(ContextReceipt)
    missing = [f for f in REQUIRED_FIELDS if f not in hints]
    assert not missing, f"ContextReceipt missing required fields: {missing}"


def test_receipt_full_file_reads_justified_and_recorded() -> None:
    """Engine issues FULL_FILE reads -> receipt carries one FullFileReadJustification per read."""
    engine = ContextEngine()
    items = [
        {
            "id": "f1",
            "content": "alpha",
            "retrieval_strategy": "FULL_FILE",
            "path": "/tmp/example.py",
            "reason": "needs full read",
            "requested_by": "node.apply",
            "byte_count": 42,
            "recency": 0.5,
            "relevance": 0.5,
            "confidence": 0.5,
        },
        {
            "id": "f2",
            "content": "beta",
            "recency": 0.5,
            "relevance": 0.5,
            "confidence": 0.5,
        },
    ]
    out = engine.build(
        task="audit",
        items=items,
        request_id="req-evidence",
        workflow="sdd",
        node="apply",
        budget=2000,
    )
    ffrs = out.receipt.full_file_reads
    assert len(ffrs) >= 1
    ffr = ffrs[0]
    assert isinstance(ffr, FullFileReadJustification)
    assert ffr.path == "/tmp/example.py"
    assert ffr.reason == "needs full read"
    assert ffr.byte_count == 42
    assert ffr.requested_by == "node.apply"


def test_legacy_v1_receipts_still_load() -> None:
    """Old receipts without ``full_file_reads`` / ``decision_dependency`` still load."""
    legacy = {
        "receipt_id": "rcpt-legacy",
        "request_id": "req-1",
        "workflow": "sdd",
        "node": "apply",
        "task": "old",
        "envelope_hash": "eh",
        "ranking_hash": "rh",
        "budget_hash": "bh",
        "included_refs": [],
        "omitted_refs": [],
        "used_tokens": 100,
        "available_tokens": 1000,
        "confidence": 0.5,
    }
    r = ContextReceipt.model_validate(legacy)
    assert r.full_file_reads == []
    assert r.decision_dependency == ""
    assert r.schema_version == "opencontext.context_receipt.v1"


def test_decision_dependency_is_required_string() -> None:
    """``decision_dependency`` must accept an empty string (required, default empty)."""
    r = ContextReceipt(
        receipt_id="x",
        request_id="x",
        workflow="w",
        node="n",
        task="t",
        decision_dependency="auth_refresh_v2",
        envelope_hash="eh",
        ranking_hash="rh",
        budget_hash="bh",
        confidence=0.5,
    )
    assert r.decision_dependency == "auth_refresh_v2"


def test_full_file_read_justification_validates() -> None:
    """FullFileReadJustification requires path/reason/byte_count/requested_by."""
    with pytest.raises(ValidationError):
        FullFileReadJustification()  # type: ignore[call-arg]
    ffr = FullFileReadJustification(
        path="/a", reason="r", byte_count=1, requested_by="node.x"
    )
    assert ffr.byte_count == 1
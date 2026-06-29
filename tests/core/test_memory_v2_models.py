"""PR-009 SPEC-MEM-009-09 / -14: MemoryQuery, MemoryConflict, MemoryReceipt models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.models.evidence import EvidenceRef
from opencontext_core.models.memory import MemoryConflict, MemoryQuery, MemoryReceipt


def test_memory_query_defaults_and_budget_fields() -> None:
    query = MemoryQuery(task="fix auth bug")
    assert query.max_records == 8
    assert query.max_tokens == 2000
    assert query.min_confidence == 0.0
    assert query.tags == []


def test_memory_conflict_typed_report() -> None:
    conflict = MemoryConflict(
        record_id="rec-old",
        candidate_summary="use bearer token",
        reason="same_key_conflicting_content",
        resolution="supersede",
    )
    assert conflict.record_id == "rec-old"
    assert conflict.resolution == "supersede"


def test_memory_receipt_ids_and_action() -> None:
    receipt = MemoryReceipt(
        memory_id="mem_123",
        action="create",
        reason="accepted",
        evidence_refs=[EvidenceRef(source="run:1", source_type="run", confidence=0.9)],
    )
    assert receipt.action == "create"
    assert receipt.receipt_id.startswith("rcpt_")
    assert receipt.memory_id == "mem_123"
    assert receipt.created_at  # ISO timestamp populated


def test_memory_receipt_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        MemoryReceipt(memory_id="m", action="explode")  # type: ignore[arg-type]

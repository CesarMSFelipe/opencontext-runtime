"""Tests for Memory v2 Pydantic models (PR-009)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


def test_REQ_mem_v2_001_round_trip() -> None:
    """A MemoryRecordV2 survives serialize -> deserialize without loss."""
    from opencontext_core.memory.v2.models import (
        MemoryKindV2,
        MemoryRecordV2,
        MemoryStatusV2,
    )

    now = datetime.now(tz=UTC)
    rec = MemoryRecordV2(
        id="mem_test001",
        kind=MemoryKindV2.DECISION,
        topic_key="architecture/auth-model",
        content="Use JWT for stateless auth",
        evidence_refs=["src/file.py:42"],
        source_refs=["run_abc"],
        confidence=0.9,
        status=MemoryStatusV2.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    payload = rec.model_dump()
    restored = MemoryRecordV2.model_validate(payload)
    assert restored == rec
    assert restored.kind is MemoryKindV2.DECISION
    assert restored.status is MemoryStatusV2.ACTIVE
    assert restored.topic_key == "architecture/auth-model"
    assert len(MemoryKindV2) == 6


def test_memory_kind_v2_has_six_values() -> None:
    from opencontext_core.memory.v2.models import MemoryKindV2

    expected = {"decision", "fact", "constraint", "error", "validation", "summary"}
    actual = {k.value for k in MemoryKindV2}
    assert actual == expected


def test_memory_candidate_v2_requires_topic_key() -> None:
    """A candidate without a topic_key cannot be deduplicated and must be rejected."""
    from opencontext_core.memory.v2.models import MemoryCandidateV2, MemoryKindV2

    with pytest.raises(ValidationError):
        MemoryCandidateV2(content="hello", kind=MemoryKindV2.FACT)


def test_memory_receipt_v2_round_trip() -> None:
    from opencontext_core.memory.v2.models import MemoryReceiptV2

    rcpt = MemoryReceiptV2(
        record_id="mem_test001",
        action="create",
        reason="promoted",
        evidence_refs=["src/file.py:42"],
    )
    payload = rcpt.model_dump()
    restored = MemoryReceiptV2.model_validate(payload)
    assert restored.record_id == "mem_test001"
    assert restored.action == "create"
    assert restored.reason == "promoted"

"""PR-009 SPEC-MEM-009-07: book-complete MemoryRecord schema (additive, defaulted)."""

from __future__ import annotations

from datetime import UTC, datetime

from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryRecord,
    MemoryStatus,
    migrate_legacy_record,
)


def _legacy_record() -> MemoryRecord:
    now = datetime.now(tz=UTC)
    # A pre-v2 call site: none of the new book fields are passed.
    return MemoryRecord(
        id="rec-1",
        layer=MemoryLayer.SEMANTIC,
        key="auth:model",
        content="Auth is centralized in AccessResolver.",
        decay_policy=DecayPolicy(enabled=False),
        created_at=now,
        updated_at=now,
    )


def test_legacy_construction_is_unaffected_with_book_defaults() -> None:
    record = _legacy_record()
    assert record.schema_version == "opencontext.memory.v1"
    assert record.scope == "project"
    assert record.status == MemoryStatus.ACTIVE
    assert record.structured == {}
    assert record.source_session_id is None
    assert record.last_seen_at is None
    assert record.quality_score == 0.0


def test_stale_status_is_representable() -> None:
    record = _legacy_record().model_copy(update={"status": MemoryStatus.STALE})
    assert record.status == "stale"


def test_status_covers_book_values() -> None:
    assert {s.value for s in MemoryStatus} == {"active", "stale", "superseded", "rejected"}


def test_migrate_legacy_record_backfills_and_stamps_version() -> None:
    now = datetime.now(tz=UTC).isoformat()
    payload = {
        "id": "old-1",
        "layer": "semantic",
        "key": "k",
        "content": "legacy belief content here",
        "decay_policy": {"enabled": False},
        "created_at": now,
        "updated_at": now,
    }
    record = migrate_legacy_record(payload)
    assert record.schema_version == "opencontext.memory.v1"
    assert record.scope == "project"
    assert record.status == MemoryStatus.ACTIVE

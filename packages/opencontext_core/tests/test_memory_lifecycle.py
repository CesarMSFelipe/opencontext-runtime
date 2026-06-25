"""Tests for D1: MemoryLifecycle field on MemoryRecord and SQLiteMemoryBackend round-trip."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryLifecycle,
    MemoryRecord,
)


def _make_record(
    lifecycle: MemoryLifecycle = MemoryLifecycle.CANDIDATE, suffix: str = ""
) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=f"test-lifecycle-{lifecycle.value}{suffix}",
        layer=MemoryLayer.EPISODIC,
        key=f"test:lifecycle{suffix}",
        content="lifecycle test record",
        decay_policy=DecayPolicy(enabled=False),
        created_at=now,
        updated_at=now,
        lifecycle=lifecycle,
    )


class TestMemoryLifecycleEnum:
    def test_all_variants_accessible(self) -> None:
        assert MemoryLifecycle.CANDIDATE == "candidate"
        assert MemoryLifecycle.ACTIVE == "active"
        assert MemoryLifecycle.SUPERSEDED == "superseded"
        assert MemoryLifecycle.EXPIRED == "expired"

    def test_default_is_candidate(self) -> None:
        now = datetime.now(tz=UTC)
        record = MemoryRecord(
            id="test-default-lifecycle",
            layer=MemoryLayer.WORKING,
            key="test:default",
            content="no lifecycle arg",
            decay_policy=DecayPolicy(enabled=False),
            created_at=now,
            updated_at=now,
        )
        assert record.lifecycle == MemoryLifecycle.CANDIDATE

    def test_no_typeerror_without_lifecycle_arg(self) -> None:
        now = datetime.now(tz=UTC)
        # Should not raise
        record = MemoryRecord(
            id="test-no-lifecycle-arg",
            layer=MemoryLayer.SEMANTIC,
            key="test:no-lc",
            content="existing caller",
            decay_policy=DecayPolicy(enabled=True),
            created_at=now,
            updated_at=now,
        )
        assert record.lifecycle is not None

    def test_explicit_lifecycle_values(self) -> None:
        for lc in MemoryLifecycle:
            rec = _make_record(lc, suffix=f"-{lc.value}")
            assert rec.lifecycle == lc


class TestSQLiteMemoryBackendLifecycle:
    def test_round_trip_lifecycle(self) -> None:
        from opencontext_core.memory.backends import SQLiteMemoryBackend

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "mem.db"
            backend = SQLiteMemoryBackend(db)

            for lc in MemoryLifecycle:
                record = _make_record(lc, suffix=f"-rt-{lc.value}")
                backend.store(record)
                results = backend.search("lifecycle test record")
                found = next((r for r in results if r.id == record.id), None)
                assert found is not None, f"Record not found for lifecycle={lc}"
                assert found.lifecycle == lc, f"Expected {lc}, got {found.lifecycle}"

    def test_migration_adds_lifecycle_column(self) -> None:
        """Existing DBs without lifecycle column get the column via _migrate()."""
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "old.db")
            # Create a pre-lifecycle DB without the column.
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_records (
                    id TEXT PRIMARY KEY,
                    layer TEXT NOT NULL,
                    key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    source_refs TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL DEFAULT '[]',
                    linked_nodes TEXT NOT NULL DEFAULT '[]',
                    supersedes TEXT NOT NULL DEFAULT '[]',
                    contradicted_by TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                    USING fts5(id UNINDEXED, layer, key, content, tags,
                               content='memory_records', content_rowid='rowid')
            """)
            conn.commit()
            conn.close()

            # Opening with SQLiteMemoryBackend should migrate without error.
            from opencontext_core.memory.backends import SQLiteMemoryBackend

            SQLiteMemoryBackend(db_path)
            # Verify column was added.
            conn2 = sqlite3.connect(db_path)
            cols = {row[1] for row in conn2.execute("PRAGMA table_info(memory_records)")}
            conn2.close()
            assert "lifecycle" in cols

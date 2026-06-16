"""LocalMemoryStore.maintain() — the consolidate+decay sweep.

Without a sweep the consolidation machinery never runs (the write path stores
records cheaply and never blocks on distillation), so near-duplicate
low-confidence records accrete. maintain() activates it across every key.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


def _store(tmp_path: Path) -> LocalMemoryStore:
    return LocalMemoryStore(tmp_path / "memory.db")


def _noisy_record(key: str, n: int) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=f"{key}-{n}",
        layer=MemoryLayer.SEMANTIC,
        key=key,
        content=f"observation {n} about {key}",
        confidence=0.3,  # low -> eligible for distillation
        source_refs=[],
        decay_policy=DecayPolicy(enabled=True),
        tags=[],
        linked_nodes=[],
        created_at=now,
        updated_at=now,
        valid_from=now,
    )


def test_maintain_consolidates_noisy_clusters(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(4):  # >= consolidation min (3)
        store._backend.store(_noisy_record("auth", i))

    report = store.maintain()

    assert report.keys_scanned == 1
    assert report.keys_consolidated == 1
    # The 4 originals are superseded; one consolidated summary remains active.
    active = store.active_records("auth")
    assert len(active) == 1
    assert "consolidated" in active[0].tags


def test_maintain_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for i in range(4):
        store._backend.store(_noisy_record("db", i))

    store.maintain()
    second = store.maintain()  # nothing new to distill
    assert second.keys_consolidated == 0


def test_maintain_noop_on_empty_store(tmp_path: Path) -> None:
    report = _store(tmp_path).maintain()
    assert report.keys_scanned == 0
    assert report.keys_consolidated == 0
    assert report.records_pruned == 0

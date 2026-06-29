"""VDM-004: MemoryStoreProvider.write routes on runtime.memory_v2_enabled.

Flag ON  → durable writes go through the MemoryHarness 8-step lifecycle (the sole
           writer; emits a MemoryReceipt and named lifecycle events) — AVH-002.
Flag OFF → the legacy direct-store path runs unchanged; the harness is never
           touched and no lifecycle event fires. OFF is the legacy default.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.memory.events import MemoryEvent
from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.memory.harness import MemoryHarness
from opencontext_core.memory.provider import MemoryStoreProvider
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef
from opencontext_core.models.memory import MemoryReceipt


def _record(
    record_id: str = "r1",
    key: str = "auth:model",
    content: str = "auth lives in AccessResolver",
) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=record_id,
        layer=MemoryLayer.SEMANTIC,
        key=key,
        content=content,
        confidence=0.9,
        source_refs=[EvidenceRef(source="x.py", source_type="file", confidence=0.9)],
        decay_policy=DecayPolicy(enabled=False),
        created_at=now,
        updated_at=now,
    )


class _ExplodingHarness:
    """A harness whose write() must never be reached on the legacy (flag-off) path."""

    def write(self, record: MemoryRecord) -> MemoryReceipt:  # pragma: no cover - must not run
        raise AssertionError("flag-off legacy path must not touch the MemoryHarness")


def test_flag_on_routes_durable_write_through_harness_lifecycle() -> None:
    """memory_v2_enabled=True → harness write tail runs (receipt + lifecycle event)."""
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalMemoryStore(Path(tmp) / "mem.db")
        harness = MemoryHarness(store)
        provider = MemoryStoreProvider(store, harness=harness, memory_v2_enabled=True)

        receipt = provider.write(_record())

        assert isinstance(receipt, MemoryReceipt)
        assert receipt.memory_id
        assert store.get(receipt.memory_id) is not None
        # Proof the harness 8-step durable tail ran (a raw store.write emits no event).
        assert harness.emitter.of_type(MemoryEvent.RECORD_CREATED)


def test_flag_off_uses_legacy_store_path_not_harness() -> None:
    """memory_v2_enabled=False → record written directly to the store, harness untouched."""
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalMemoryStore(Path(tmp) / "mem.db")
        provider = MemoryStoreProvider(store, harness=_ExplodingHarness(), memory_v2_enabled=False)

        receipt = provider.write(_record())

        assert isinstance(receipt, MemoryReceipt)
        assert receipt.memory_id
        # The record was persisted directly to the store (legacy verbatim path).
        assert store.get(receipt.memory_id) is not None


def test_flag_off_emits_no_harness_lifecycle_event() -> None:
    """The legacy direct write bypasses the harness, so no lifecycle event fires."""
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalMemoryStore(Path(tmp) / "mem.db")
        harness = MemoryHarness(store)
        provider = MemoryStoreProvider(store, harness=harness, memory_v2_enabled=False)

        provider.write(_record())

        assert not harness.emitter.of_type(MemoryEvent.RECORD_CREATED)


def test_default_construction_is_legacy_path() -> None:
    """No explicit flag → legacy default (off); the harness is not invoked."""
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalMemoryStore(Path(tmp) / "mem.db")
        provider = MemoryStoreProvider(store, harness=_ExplodingHarness())

        receipt = provider.write(_record())

        assert store.get(receipt.memory_id) is not None

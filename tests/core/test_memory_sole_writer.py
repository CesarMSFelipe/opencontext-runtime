"""AVH-002: MemoryStoreProvider.write routes through the MemoryHarness (sole writer).

Anti-regression for the confirmed bypass at ``memory/provider.py`` where ``write``
called ``self._store.write(record)`` directly, skipping the harness lifecycle
(conflict-check / KG-link / receipt). With VDM-004 the harness path is gated on
``memory_v2_enabled``; these tests construct the provider with the flag ON and prove
``write`` delegates to ``MemoryHarness.write`` and that the harness lifecycle fires.
The flag-OFF legacy path is covered by ``test_memory_v2_routing.py``.
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


def _record(record_id: str, key: str, content: str) -> MemoryRecord:
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


def test_provider_write_delegates_to_harness_not_store() -> None:
    """write() calls harness.write; the raw store is never touched directly."""

    class _ExplodingStore:
        def write(self, record: MemoryRecord) -> str:  # pragma: no cover - must not run
            raise AssertionError("MemoryStoreProvider.write bypassed the harness (AVH-002)")

    class _SpyHarness:
        def __init__(self) -> None:
            self.records: list[MemoryRecord] = []

        def write(self, record: MemoryRecord) -> MemoryReceipt:
            self.records.append(record)
            return MemoryReceipt(
                memory_id="m1", action="create", reason="write", evidence_refs=[]
            )

    spy = _SpyHarness()
    provider = MemoryStoreProvider(_ExplodingStore(), harness=spy, memory_v2_enabled=True)
    receipt = provider.write(_record("r1", "auth:model", "auth lives in AccessResolver"))

    assert receipt.memory_id == "m1"
    assert len(spy.records) == 1


def test_provider_write_runs_harness_lifecycle_and_emits_event() -> None:
    """End-to-end: write persists the record AND emits a harness lifecycle event."""
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalMemoryStore(Path(tmp) / "mem.db")
        harness = MemoryHarness(store)
        provider = MemoryStoreProvider(store, harness=harness, memory_v2_enabled=True)

        receipt = provider.write(_record("r1", "auth:model", "auth lives in AccessResolver"))

        assert isinstance(receipt, MemoryReceipt)
        assert receipt.memory_id
        assert store.get(receipt.memory_id) is not None
        # Proof the harness lifecycle ran (a raw store.write emits no event).
        assert harness.emitter.of_type(MemoryEvent.RECORD_CREATED)


def test_provider_write_links_kg_through_harness() -> None:
    """The injected KG-link port fires on write — only reachable via the harness tail."""
    linked: list[str] = []

    class _Linker:
        def link_memory(self, record: MemoryRecord) -> list[str]:
            linked.append(record.id)
            return ["kg_node_1"]

    with tempfile.TemporaryDirectory() as tmp:
        store = LocalMemoryStore(Path(tmp) / "mem.db")
        harness = MemoryHarness(store, kg_linker=_Linker())
        provider = MemoryStoreProvider(store, harness=harness, memory_v2_enabled=True)

        provider.write(_record("r1", "db:migrate", "migrations run via the migrate command"))

        assert linked  # KG-link port invoked during the harness write tail

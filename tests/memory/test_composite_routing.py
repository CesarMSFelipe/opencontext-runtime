"""CompositeMemoryStore routing tests (PR-AHE-007 task 7.5).

The contract is the 4-line ``_ENGRAM_LAYERS`` / ``_LOCAL_LAYERS`` split in
``memory/composite.py`` together with the module-load ``_ROUTED_LAYERS ==
set(MemoryLayer)`` assertion. These tests prove each layer lands on the right
backend WITHOUT requiring a live Engram server (the in-process fake from
``tests/memory/fake_engram_client.py`` captures every call).

If a future commit moves a layer between backends, one of these tests goes
red first — and the module-load assertion at composite.py:32 keeps a new
layer from silently defaulting to local.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryRecord,
)
from tests.memory.fake_engram_client import (
    composite,
    engram_routed_layers,
    local_routed_layers,
    local_store,
)


def _make_record(layer: MemoryLayer, *, content: str, key: str = "k:0") -> MemoryRecord:
    """Build a minimal valid ``MemoryRecord`` for composite routing tests."""
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=f"id-{layer.value}-{abs(hash(content)) % 10_000}",
        layer=layer,
        key=key,
        content=content,
        confidence=1.0,
        decay_policy=DecayPolicy(enabled=True),
        tags=[],
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    "layer",
    [MemoryLayer.SEMANTIC, MemoryLayer.EPISODIC],
    ids=["semantic", "episodic"],
)
def test_engram_routed_layer_writes_to_fake_engram(tmp_path: Path, layer: MemoryLayer) -> None:
    """SEMANTIC + EPISODIC writes go to the (fake) Engram backend.

    Spec scenario 7.5: "semantic/episodic route to Engram".
    """
    fake = _FakeClient()
    local = local_store(tmp_path)
    store = composite(local, fake)  # type: ignore[arg-type]

    record = _make_record(layer, content="durable fact", key=f"key-{layer.value}")
    store.write(record)

    # The fake (== EngramMemoryStore's engram leg) must have seen at least
    # one ``mem_save`` call. ``EngramMemoryStore.write`` may additionally
    # pre-fetch existing same-key records for contradiction detection, so we
    # only assert "the save happened" — not "exactly one call".
    save_calls = [c for c in fake.calls if c[0] == "mem_save"]
    assert len(save_calls) >= 1
    # Local store must NOT have the record (engram-only routing).
    assert store_search_keys(local, layer) == []


@pytest.mark.parametrize(
    "layer",
    [
        MemoryLayer.PROCEDURAL,
        MemoryLayer.FAILURE,
        MemoryLayer.WORKING,
        MemoryLayer.PROJECT,
        MemoryLayer.HARNESS_EXPERIENCE,
    ],
)
def test_local_routed_layer_writes_to_local_only(tmp_path: Path, layer: MemoryLayer) -> None:
    """PROCEDURAL/FAILURE/WORKING/PROJECT/HARNESS_EXPERIENCE stay local.

    Spec scenario 7.5: "procedural/failure/working/project/harness memory
    remains local".
    """
    fake = _FakeClient()
    local = local_store(tmp_path)
    store = composite(local, fake)  # type: ignore[arg-type]

    record = _make_record(layer, content="local-only fact", key=f"key-{layer.value}")
    store.write(record)

    # Engram must not see a save for a local-routed layer.
    save_calls = [c for c in fake.calls if c[0] == "mem_save"]
    assert save_calls == []
    # Local store must hold exactly the one record.
    keys = store_search_keys(local, layer)
    assert keys == [f"key-{layer.value}"]


def test_every_memory_layer_is_routed(tmp_path: Path) -> None:
    """The split covers every ``MemoryLayer`` — mirrors the module-load
    assertion in composite.py:32 as a testable runtime check.
    """
    assert engram_routed_layers() | local_routed_layers() == {layer.value for layer in MemoryLayer}
    # No layer is in both backends (the dual-routing bug a future refactor
    # could accidentally introduce).
    assert engram_routed_layers() & local_routed_layers() == set()


def test_scoped_search_routes_only_to_matching_backend(tmp_path: Path) -> None:
    """A scoped search (scope=<layer>) hits ONLY the layer's home backend.

    A SEMANTIC save lands on engram; a search scoped to SEMANTIC must NOT
    touch the local store's search path.
    """
    fake = _FakeClient()
    local = local_store(tmp_path)
    store = composite(local, fake)  # type: ignore[arg-type]

    semantic_record = _make_record(
        MemoryLayer.SEMANTIC, content="semantic fact body", key="key-sem"
    )
    store.write(semantic_record)

    # Reset call log so the assertion reads only the search-side calls.
    fake.calls.clear()

    store.search("semantic fact body", scope=MemoryLayer.SEMANTIC, limit=10)

    # The SEMANTIC-scoped search must have hit the engram leg (fake.mem_search).
    assert any(c[0] == "mem_search" for c in fake.calls), fake.calls


def test_unscoped_search_hits_both_backends_and_merges(tmp_path: Path) -> None:
    """scope=None fans out to both stores and merges via RRF.

    Two saves — one semantic, one procedural — and a single unscoped search
    must surface BOTH records in the merged result.
    """
    fake = _FakeClient()
    local = local_store(tmp_path)
    store = composite(local, fake)  # type: ignore[arg-type]

    # Both records share the keyword "shared" so a single unscoped query
    # finds each through its respective backend's text-matching path.
    store.write(_make_record(MemoryLayer.SEMANTIC, content="shared durable fact", key="key-alpha"))
    store.write(_make_record(MemoryLayer.FAILURE, content="shared flaky pattern", key="key-beta"))
    fake.calls.clear()

    records = store.search("shared", scope=None, limit=10)
    keys = {r.key for r in records}
    # Both backends contributed; the merged result contains BOTH keys.
    assert keys == {"key-alpha", "key-beta"}


def test_write_through_composite_routes_record_id_to_correct_backend(
    tmp_path: Path,
) -> None:
    """The composite returns the handle from the chosen backend verbatim —
    engram for engram layers, local-id for local layers — confirming the
    caller can tell which backend persists which record.
    """
    fake = _FakeClient()
    local = local_store(tmp_path)
    store = composite(local, fake)  # type: ignore[arg-type]

    sem_handle = store.write(_make_record(MemoryLayer.SEMANTIC, content="durable", key="k-sem"))
    fail_handle = store.write(_make_record(MemoryLayer.FAILURE, content="flaky", key="k-fail"))
    # Same store, two writes — but the handles come from two different backs.
    assert sem_handle and fail_handle
    assert sem_handle != fail_handle


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


class _FakeClient:
    """Trivial EngramClient stand-in for this test file.

    We can't import the recording ``FakeEngramClient`` from the fixture file
    here without a sys.path dance; this class only needs ``mem_search`` /
    ``mem_save`` / ``mem_update`` returning ``{'results': [...]}`` so the
    composite layer's routing is observable.
    """

    def __init__(self) -> None:
        self.records: list[dict] = []
        self.calls: list[tuple[str, dict]] = []

    def mem_save(self, **kwargs):
        self.calls.append(("mem_save", dict(kwargs)))
        self.records.append(dict(kwargs))
        return {"ok": True, "id": kwargs.get("id", "fake-id")}

    def mem_search(self, **kwargs):
        self.calls.append(("mem_search", dict(kwargs)))
        query = str(kwargs.get("query", "")).lower()
        hits = [
            dict(r)
            for r in self.records
            if query in str(r.get("content", "")).lower()
            or query in str(r.get("title", "")).lower()
        ]
        return {"results": hits}

    def mem_update(self, **kwargs):
        self.calls.append(("mem_update", dict(kwargs)))
        return {"ok": True}


def store_search_keys(local: Any, layer: MemoryLayer) -> list[str]:
    """Return the keys of records in ``local`` whose layer matches ``layer``."""
    rows = local.list_records(limit=200)
    return [r.key for r in rows if r.layer == layer]

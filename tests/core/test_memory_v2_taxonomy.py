"""PR-009 SPEC-MEM-009-11: six-type taxonomy + every layer routed in composite."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opencontext_core.memory.composite import _ENGRAM_LAYERS, _LOCAL_LAYERS
from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


@pytest.fixture()
def store() -> LocalMemoryStore:
    with tempfile.TemporaryDirectory() as tmp:
        yield LocalMemoryStore(Path(tmp) / "mem.db")


def test_six_type_taxonomy_present() -> None:
    names = {layer.value for layer in MemoryLayer}
    for expected in (
        "episodic",
        "semantic",
        "procedural",
        "project",
        "failure",
        "harness_experience",
    ):
        assert expected in names


def test_every_layer_is_routed_exactly_once() -> None:
    routed = _ENGRAM_LAYERS | _LOCAL_LAYERS
    assert routed == set(MemoryLayer)
    assert not (_ENGRAM_LAYERS & _LOCAL_LAYERS)
    assert MemoryLayer.PROJECT in _LOCAL_LAYERS
    assert MemoryLayer.HARNESS_EXPERIENCE in _LOCAL_LAYERS


def test_harness_experience_record_round_trips(store: LocalMemoryStore) -> None:
    now = datetime.now(tz=UTC)
    record = MemoryRecord(
        id="he-1",
        layer=MemoryLayer.HARNESS_EXPERIENCE,
        key="harness:experience:1",
        content="OC Flow ran best with surgical explore on this repo.",
        decay_policy=DecayPolicy(enabled=False),
        created_at=now,
        updated_at=now,
    )
    store.write(record)
    found = store.search("surgical explore", scope=MemoryLayer.HARNESS_EXPERIENCE)
    assert any(r.id == "he-1" for r in found)

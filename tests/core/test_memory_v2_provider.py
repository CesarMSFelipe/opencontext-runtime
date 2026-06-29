"""PR-009 SPEC-MEM-009-10: book MemoryProvider Protocol surface + store adapter."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.memory.provider import MemoryProvider, MemoryStoreProvider
from opencontext_core.memory_usability.memory_candidates import MemoryCandidate, MemoryKind
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.models.context import DataClassification
from opencontext_core.models.evidence import EvidenceRef
from opencontext_core.models.memory import MemoryConflict, MemoryQuery, MemoryReceipt


@pytest.fixture()
def provider() -> MemoryStoreProvider:
    with tempfile.TemporaryDirectory() as tmp:
        yield MemoryStoreProvider(LocalMemoryStore(Path(tmp) / "mem.db"))


def _record(record_id: str, key: str, content: str, confidence: float = 0.9) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=record_id,
        layer=MemoryLayer.SEMANTIC,
        key=key,
        content=content,
        confidence=confidence,
        source_refs=[EvidenceRef(source="x.py", source_type="file", confidence=0.9)],
        decay_policy=DecayPolicy(enabled=False),
        created_at=now,
        updated_at=now,
    )


def test_store_adapter_satisfies_protocol(provider: MemoryStoreProvider) -> None:
    assert isinstance(provider, MemoryProvider)


def test_write_get_search_round_trip(provider: MemoryStoreProvider) -> None:
    receipt = provider.write(_record("r1", "auth:model", "auth lives in AccessResolver module"))
    assert isinstance(receipt, MemoryReceipt)
    assert receipt.action in {"create", "update"}
    got = provider.get(receipt.memory_id)
    assert got is not None
    results = provider.search(MemoryQuery(task="AccessResolver", max_records=5))
    assert any(r.id == receipt.memory_id for r in results)


def test_detect_conflicts_returns_typed(provider: MemoryStoreProvider) -> None:
    provider.write(_record("r1", "auth:flow", "auth uses cookie sessions", confidence=0.9))
    candidate = MemoryCandidate(
        content="auth uses bearer tokens instead",
        source="trace:2",
        kind=MemoryKind.FACT,
        novelty_score=0.7,
        reuse_likelihood=0.7,
        classification=DataClassification.INTERNAL,
        token_cost=10,
        evidence_refs=[EvidenceRef(source="auth.py", source_type="file", confidence=0.3)],
        confidence=0.3,
        metadata={"key": "auth:flow"},
    )
    conflicts = provider.detect_conflicts(candidate)
    assert all(isinstance(c, MemoryConflict) for c in conflicts)
    assert any(c.record_id == "r1" for c in conflicts)

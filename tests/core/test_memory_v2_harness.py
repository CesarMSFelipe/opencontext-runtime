"""PR-009 SPEC-MEM-009-12 / -09: MemoryHarness sole-writer lifecycle + receipts/events."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from opencontext_core.memory.events import MemoryEvent
from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.memory.harness import KgLinkPort, MemoryHarness
from opencontext_core.memory_usability.memory_candidates import MemoryCandidate, MemoryKind
from opencontext_core.models.agent_memory import MemoryRecord
from opencontext_core.models.context import DataClassification
from opencontext_core.models.evidence import EvidenceRef


def _candidate(content: str, *, evidence: bool = True) -> MemoryCandidate:
    refs = [EvidenceRef(source="auth.py", source_type="file", confidence=0.9)] if evidence else []
    return MemoryCandidate(
        content=content,
        source="trace:1",
        kind=MemoryKind.FACT,
        novelty_score=0.7,
        reuse_likelihood=0.7,
        classification=DataClassification.INTERNAL,
        token_cost=20,
        proposed_by="test",
        evidence_refs=refs,
        confidence=0.8,
    )


@pytest.fixture()
def store() -> LocalMemoryStore:
    with tempfile.TemporaryDirectory() as tmp:
        yield LocalMemoryStore(Path(tmp) / "mem.db")


def test_create_receipt_and_persisted_record(store: LocalMemoryStore) -> None:
    harness = MemoryHarness(store)
    receipt = harness.promote(_candidate("The gateway service refreshes auth tokens every hour."))
    assert receipt.action == "create"
    assert receipt.memory_id
    persisted = store.get(receipt.memory_id)
    assert persisted is not None
    assert persisted.provenance == "harness"
    assert harness.emitter.of_type(MemoryEvent.RECORD_CREATED)


def test_chain_of_thought_candidate_is_rejected(store: LocalMemoryStore) -> None:
    harness = MemoryHarness(store)
    receipt = harness.promote(
        _candidate("Let me think step by step about the gateway auth flow here.")
    )
    assert receipt.action == "reject"
    assert receipt.reason == "chain_of_thought_excluded"
    # No durable record persisted.
    assert store.list_records() == []
    assert harness.emitter.of_type(MemoryEvent.CANDIDATE_REJECTED)


def test_evidence_less_candidate_is_rejected(store: LocalMemoryStore) -> None:
    harness = MemoryHarness(store)
    receipt = harness.promote(
        _candidate("The gateway service refreshes auth tokens every hour.", evidence=False)
    )
    assert receipt.action == "reject"
    assert receipt.reason == "evidence_missing"
    assert store.list_records() == []


def test_kg_link_port_is_invoked(store: LocalMemoryStore) -> None:
    calls: list[str] = []

    class _Linker:
        def link_memory(self, record: MemoryRecord) -> list[str]:
            calls.append(record.id)
            return ["kg_node_1"]

    linker: KgLinkPort = _Linker()
    harness = MemoryHarness(store, kg_linker=linker)
    receipt = harness.promote(
        _candidate("Database migrations are applied via the migrate command.")
    )
    assert receipt.action == "create"
    assert calls  # KG link port was called during the lifecycle

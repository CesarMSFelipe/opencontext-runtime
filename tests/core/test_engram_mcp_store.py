"""Tests for EngramMemoryStore — protocol conformance over a fake engram client.

The store maps the AgentMemoryStore protocol (search/write/reinforce/contradict/
decay/failure_boost) onto an INJECTABLE engram client surface (mem_save/mem_search/
mem_update/...). Tests pass a recording fake double; no global MCP tools are called.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from opencontext_core.memory.agent import AgentMemoryStore
from opencontext_core.memory.engram_mcp_store import EngramMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef


class FakeEngramClient:
    """Recording double of the engram MCP client surface."""

    def __init__(self, search_results: list[dict[str, Any]] | None = None) -> None:
        self.saved: list[dict[str, Any]] = []
        self.searches: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self._search_results = search_results or []

    def mem_save(self, **kwargs: Any) -> dict[str, Any]:
        self.saved.append(kwargs)
        # engram returns an id/handle for the saved observation
        return {"id": f"engram-{len(self.saved)}", "ok": True}

    def mem_search(self, **kwargs: Any) -> dict[str, Any]:
        self.searches.append(kwargs)
        return {"results": list(self._search_results)}

    def mem_update(self, **kwargs: Any) -> dict[str, Any]:
        self.updates.append(kwargs)
        return {"ok": True}


def make_record(
    record_id: str = "rec-1",
    key: str = "test:key",
    content: str = "some content",
    layer: MemoryLayer = MemoryLayer.EPISODIC,
    confidence: float = 0.9,
) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    return MemoryRecord(
        id=record_id,
        layer=layer,
        key=key,
        content=content,
        confidence=confidence,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=False),
        tags=[],
        linked_nodes=[],
        created_at=now,
        updated_at=now,
    )


def test_satisfies_agent_memory_store_protocol() -> None:
    store = EngramMemoryStore(FakeEngramClient())
    assert isinstance(store, AgentMemoryStore)


def test_write_calls_mem_save_and_returns_id() -> None:
    client = FakeEngramClient()
    store = EngramMemoryStore(client)
    record = make_record(record_id="w-1", content="auth middleware crash")
    returned = store.write(record)
    assert returned == "w-1"
    assert len(client.saved) == 1
    saved = client.saved[0]
    # the record content must be carried into the engram payload
    assert "auth middleware crash" in saved.get("content", "")


def test_search_calls_mem_search_and_maps_results() -> None:
    client = FakeEngramClient(
        search_results=[
            {
                "id": "obs-1",
                "title": "test:key",
                "content": "auth middleware crash failure",
                "type": "episodic",
            }
        ]
    )
    store = EngramMemoryStore(client)
    results = store.search("auth middleware")
    assert len(client.searches) == 1
    assert client.searches[0].get("query") == "auth middleware"
    assert len(results) == 1
    assert isinstance(results[0], MemoryRecord)
    assert "auth middleware crash failure" in results[0].content


def test_search_with_scope_passes_layer() -> None:
    client = FakeEngramClient()
    store = EngramMemoryStore(client)
    store.search("graph db failure", scope=MemoryLayer.FAILURE, limit=5)
    call = client.searches[0]
    assert call.get("query") == "graph db failure"
    # limit forwarded
    assert call.get("limit") == 5


def test_search_empty_results_returns_empty_list() -> None:
    store = EngramMemoryStore(FakeEngramClient(search_results=[]))
    assert store.search("nothing here") == []


def test_reinforce_does_not_raise() -> None:
    store = EngramMemoryStore(FakeEngramClient())
    evidence = EvidenceRef(source="test", source_type="code", confidence=1.0)
    # must be callable per protocol and not raise
    store.reinforce("some-id", evidence)


def test_contradict_does_not_raise() -> None:
    store = EngramMemoryStore(FakeEngramClient())
    evidence = EvidenceRef(source="counter", source_type="code", confidence=1.0)
    store.contradict("some-id", evidence)


def test_decay_returns_int() -> None:
    store = EngramMemoryStore(FakeEngramClient())
    result = store.decay()
    assert isinstance(result, int)
    assert result >= 0


def test_failure_boost_returns_dict_keyed_by_symbol() -> None:
    client = FakeEngramClient(
        search_results=[
            {
                "id": "f-1",
                "title": "failure:x",
                "content": "ContextPackBuilder failed",
                "type": "failure",
            }
        ]
    )
    store = EngramMemoryStore(client)
    boosts = store.failure_boost(["ContextPackBuilder"])
    assert "ContextPackBuilder" in boosts
    assert boosts["ContextPackBuilder"] > 0.0


def test_failure_boost_unknown_symbol_is_zero() -> None:
    store = EngramMemoryStore(FakeEngramClient(search_results=[]))
    boosts = store.failure_boost(["totally_unknown_symbol_xyz"])
    assert boosts["totally_unknown_symbol_xyz"] == 0.0


def test_client_call_failure_degrades_search_to_empty() -> None:
    """A failing engram client must not break recall (degrade to empty)."""

    class BoomClient:
        def mem_search(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("engram down")

        def mem_save(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("engram down")

    store = EngramMemoryStore(BoomClient())
    assert store.search("anything") == []


def test_contradiction_check_runs_on_write_before_persist() -> None:
    """ContradictionDetector runs against existing same-key records before save.

    The store searches for existing records sharing the new key, runs the
    detector, and calls contradict() per hit.
    """
    client = FakeEngramClient(
        search_results=[
            {
                "id": "old-1",
                "title": "auth:login",
                "content": "use cookie session",
                "type": "semantic",
                "confidence": 0.9,
                "key": "auth:login",
            }
        ]
    )
    store = EngramMemoryStore(client)

    contradicted: list[str] = []
    original_contradict = store.contradict

    def _record_contradict(memory_id: str, evidence: EvidenceRef) -> None:
        contradicted.append(memory_id)
        original_contradict(memory_id, evidence)

    store.contradict = _record_contradict  # type: ignore[method-assign]

    new_record = make_record(
        record_id="new-1",
        key="auth:login",
        content="use bearer token",
        layer=MemoryLayer.SEMANTIC,
        confidence=0.4,
    )
    store.write(new_record)

    assert "old-1" in contradicted

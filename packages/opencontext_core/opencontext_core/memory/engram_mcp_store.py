"""EngramMemoryStore: AgentMemoryStore implemented over an injectable engram client.

This store maps the `AgentMemoryStore` protocol (search/write/reinforce/contradict/
decay/failure_boost) onto an engram client surface (mem_save/mem_search/mem_update).

The engram client is INJECTED (a small structural protocol), so tests pass a
fake/recording double. This module never hard-calls global MCP tools — all
transport is delegated to the injected client. When the client raises, recall
degrades to empty rather than propagating the failure.

`ContradictionDetector` runs on every `write` before the record is persisted:
existing records sharing the new record's key are fetched, the detector flags
contradictions, and `contradict(id, evidence)` is called for each hit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from opencontext_core.memory.contradictions import ContradictionDetector
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryRecord,
)
from opencontext_core.models.evidence import EvidenceRef


@runtime_checkable
class EngramClient(Protocol):
    """Minimal structural surface of the engram MCP client used by the store.

    Only the methods the store actually drives are declared. Real callers
    provide a thin adapter around the engram MCP tools; tests provide a
    recording double.
    """

    def mem_save(self, **kwargs: Any) -> Any: ...

    def mem_search(self, **kwargs: Any) -> Any: ...


def _extract_results(raw: Any) -> list[dict[str, Any]]:
    """Normalize an engram search response into a list of result dicts."""
    results: Any
    if raw is None:
        return []
    if isinstance(raw, dict):
        results = raw.get("results", raw.get("observations", []))
    elif isinstance(raw, list):
        results = raw
    else:
        results = getattr(raw, "results", [])
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict)]


def _result_to_record(item: dict[str, Any], *, layer: MemoryLayer) -> MemoryRecord:
    """Map an engram search-result dict into a MemoryRecord (best effort)."""
    now = datetime.now(tz=UTC)
    type_value = item.get("type")
    record_layer = layer
    if isinstance(type_value, str):
        try:
            record_layer = MemoryLayer(type_value)
        except ValueError:
            record_layer = layer
    confidence = item.get("confidence", 1.0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 1.0
    confidence = max(0.0, min(1.0, confidence))
    return MemoryRecord(
        id=str(item.get("id") or item.get("observation_id") or ""),
        layer=record_layer,
        key=str(item.get("key") or item.get("topic_key") or item.get("title") or ""),
        content=str(item.get("content") or item.get("title") or ""),
        confidence=confidence,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=True, half_life_days=90),
        tags=[],
        linked_nodes=[],
        created_at=now,
        updated_at=now,
    )


class EngramMemoryStore:
    """AgentMemoryStore backed by an injected engram client.

    Implements the AgentMemoryStore Protocol.
    """

    def __init__(
        self,
        client: EngramClient,
        *,
        project: str = "default",
        detector: ContradictionDetector | None = None,
    ) -> None:
        self._client = client
        self._project = project
        self._detector = detector or ContradictionDetector()

    def _search_raw(
        self, query: str, *, limit: int, layer: MemoryLayer | None
    ) -> list[dict[str, Any]]:
        if not query.strip():
            return []
        kwargs: dict[str, Any] = {"query": query, "limit": limit}
        if layer is not None:
            kwargs["type"] = layer.value
        try:
            raw = self._client.mem_search(**kwargs)
        except Exception:
            return []
        return _extract_results(raw)

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        items = self._search_raw(query, limit=limit, layer=scope)
        records = [_result_to_record(item, layer=scope or MemoryLayer.SEMANTIC) for item in items]
        if scope is not None:
            records = [r for r in records if r.layer == scope]
        return records

    def write(self, memory: MemoryRecord) -> str:
        # Contradiction-on-write: detect against existing same-key records first.
        try:
            existing_raw = self._search_raw(memory.key, limit=20, layer=None)
        except Exception:
            existing_raw = []
        existing = [_result_to_record(item, layer=memory.layer) for item in existing_raw]
        existing = [r for r in existing if r.key == memory.key and r.id]
        contradicted_ids = self._detector.detect(memory, existing)
        evidence = EvidenceRef(source=memory.id, source_type="memory", confidence=memory.confidence)
        for contradicted_id in contradicted_ids:
            self.contradict(contradicted_id, evidence)

        try:
            self._client.mem_save(
                title=memory.key,
                content=memory.content,
                type=memory.layer.value,
                topic_key=memory.key,
                project=self._project,
                capture_prompt=False,
            )
        except Exception:
            # Persist failure must not raise; callers treat the local id as the handle.
            pass
        return memory.id

    def reinforce(self, memory_id: str, evidence: EvidenceRef) -> None:
        # Confidence reinforcement is a best-effort update on the engram side.
        update = getattr(self._client, "mem_update", None)
        if update is None:
            return
        try:
            update(observation_id=memory_id, action="reinforce")
        except Exception:
            return

    def contradict(self, memory_id: str, evidence: EvidenceRef) -> None:
        update = getattr(self._client, "mem_update", None)
        if update is None:
            return
        ref_id = getattr(evidence, "source", str(evidence))
        try:
            update(observation_id=memory_id, action="contradict", evidence=ref_id)
        except Exception:
            return

    def decay(self) -> int:
        # Engram manages its own retention; nothing to prune client-side.
        return 0

    def failure_boost(self, symbols: list[str]) -> dict[str, float]:
        boosts: dict[str, float] = {}
        for symbol in symbols:
            items = self._search_raw(symbol, limit=20, layer=MemoryLayer.FAILURE)
            failure_items = [
                item for item in items if str(item.get("type", "")) == MemoryLayer.FAILURE.value
            ] or items
            if not failure_items:
                boosts[symbol] = 0.0
                continue
            boosts[symbol] = min(0.15 * len(failure_items), 1.0)
        return boosts

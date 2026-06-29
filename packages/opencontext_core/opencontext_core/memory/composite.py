"""CompositeMemoryStore — routes writes and searches by MemoryLayer.

EPISODIC / SEMANTIC  → EngramMemoryStore (long-term, external)
PROCEDURAL / FAILURE / WORKING / PROJECT / HARNESS_EXPERIENCE
    → LocalMemoryStore (SQLite, fast, private)

PR-009 adds ``PROJECT`` and ``HARNESS_EXPERIENCE`` as repo-local curation layers;
both route to the local store (Engram stays semantic/episodic only). A module-load
assertion guarantees every ``MemoryLayer`` is explicitly routed so a future layer
addition can never silently default.

When scope=None, both stores are searched and results are merged via RRF.
Both backing stores are unchanged; this class only adds routing.
"""

from __future__ import annotations

import logging

from opencontext_core.memory.agent import AgentMemoryStore
from opencontext_core.memory.fusion import reciprocal_rank_fusion
from opencontext_core.models.agent_memory import MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef

_log = logging.getLogger(__name__)

_ENGRAM_LAYERS = {MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC}
_LOCAL_LAYERS = {
    MemoryLayer.PROCEDURAL,
    MemoryLayer.FAILURE,
    MemoryLayer.WORKING,
    MemoryLayer.PROJECT,
    MemoryLayer.HARNESS_EXPERIENCE,
}

# Anti-regression: every MemoryLayer must be routed to exactly one backend so a
# new layer cannot silently default to local (PR-009 SPEC-MEM-009-11).
_ROUTED_LAYERS = _ENGRAM_LAYERS | _LOCAL_LAYERS
assert _ROUTED_LAYERS == set(MemoryLayer), (
    "every MemoryLayer must be routed in composite.py; "
    f"unrouted: {set(MemoryLayer) - _ROUTED_LAYERS}"
)
assert not (_ENGRAM_LAYERS & _LOCAL_LAYERS), "a MemoryLayer is routed to two backends"


class CompositeMemoryStore:
    """Routes AgentMemoryStore operations by MemoryLayer."""

    def __init__(self, local: AgentMemoryStore, engram: AgentMemoryStore) -> None:
        self._local = local
        self._engram = engram

    def _store_for_layer(self, layer: MemoryLayer | None) -> AgentMemoryStore:
        if layer in _ENGRAM_LAYERS:
            return self._engram
        return self._local

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        if scope is not None:
            return self._store_for_layer(scope).search(query, scope=scope, limit=limit)

        # scope=None: merge both stores via RRF
        local_results = self._local.search(query, scope=None, limit=limit)
        engram_results = self._engram.search(query, scope=None, limit=limit)

        all_by_id: dict[str, MemoryRecord] = {r.id: r for r in local_results}
        all_by_id.update({r.id: r for r in engram_results})

        id_lists = [
            [r.id for r in local_results],
            [r.id for r in engram_results],
        ]
        ranked_ids = reciprocal_rank_fusion(id_lists)
        return [all_by_id[rid] for rid in ranked_ids[:limit] if rid in all_by_id]

    def write(self, memory: MemoryRecord) -> str:
        store = self._store_for_layer(memory.layer)
        handle = store.write(memory)
        # Durability fallback: if the engram-routed write did not persist (empty
        # handle), keep the memory locally rather than silently dropping it.
        if store is self._engram and not handle:
            _log.warning(
                "engram write did not persist (key=%r, layer=%s); falling back to local store",
                memory.key,
                memory.layer.value,
            )
            return self._local.write(memory)
        return handle

    def reinforce(self, memory_id: str, evidence: EvidenceRef) -> None:
        # Try local first, then engram; both are no-ops if ID not found
        self._local.reinforce(memory_id, evidence)
        self._engram.reinforce(memory_id, evidence)

    def contradict(self, memory_id: str, evidence: EvidenceRef) -> None:
        self._local.contradict(memory_id, evidence)
        self._engram.contradict(memory_id, evidence)

    def decay(self) -> int:
        # Only local tracks procedural/failure/working — engram manages its own TTL
        return self._local.decay()

    def failure_boost(self, symbols: list[str]) -> dict[str, float]:
        return self._local.failure_boost(symbols)

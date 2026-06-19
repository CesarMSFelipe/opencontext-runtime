"""CompositeMemoryStore — routes writes and searches by MemoryLayer.

EPISODIC / SEMANTIC  → EngramMemoryStore (long-term, external)
PROCEDURAL / FAILURE / WORKING → LocalMemoryStore (SQLite, fast, private)

When scope=None, both stores are searched and results are merged via RRF.
Both backing stores are unchanged; this class only adds routing.
"""

from __future__ import annotations

from opencontext_core.memory.agent import AgentMemoryStore
from opencontext_core.memory.fusion import reciprocal_rank_fusion
from opencontext_core.models.agent_memory import MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef

_ENGRAM_LAYERS = {MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC}
_LOCAL_LAYERS = {MemoryLayer.PROCEDURAL, MemoryLayer.FAILURE, MemoryLayer.WORKING}


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
        return self._store_for_layer(memory.layer).write(memory)

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

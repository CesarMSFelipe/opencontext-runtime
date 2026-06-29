"""MemoryProvider — book OC-MEMORY-001 §26 Protocol surface + a store adapter.

PR-009 aligns this module to the book provider surface:
``search(MemoryQuery)`` / ``get`` / ``write(record) -> MemoryReceipt`` /
``supersede(old_id, new) -> MemoryReceipt`` / ``detect_conflicts(candidate) ->
list[MemoryConflict]``. Upper layers depend on the ``MemoryProvider`` Protocol,
not a concrete store.

The legacy ``provider.py:MemoryRecord`` key/value/tags dataclass (no importers)
is removed in favor of aliasing the canonical
``models.agent_memory.MemoryRecord`` so there is one true record type.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from opencontext_core.memory.contradictions import ContradictionDetector
from opencontext_core.memory.harness import MemoryHarness
from opencontext_core.memory.kind_classifier import classify_kind
from opencontext_core.memory_usability.memory_candidates import MemoryCandidate
from opencontext_core.models.agent_memory import MemoryLayer
from opencontext_core.models.agent_memory import MemoryRecord as MemoryRecord  # canonical alias
from opencontext_core.models.memory import MemoryConflict, MemoryQuery, MemoryReceipt


@runtime_checkable
class MemoryProvider(Protocol):
    """Book memory backend surface used by upper layers (OC-MEMORY-001 §26)."""

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        """Return records relevant to a typed query, honoring its budgets."""
        ...

    def get(self, memory_id: str) -> MemoryRecord | None:
        """Fetch a single record by id, or None."""
        ...

    def write(self, record: MemoryRecord) -> MemoryReceipt:
        """Persist a record (consolidating against active beliefs); return a receipt."""
        ...

    def supersede(self, old_id: str, new: MemoryRecord) -> MemoryReceipt:
        """Replace ``old_id`` with ``new`` preserving lineage; return a receipt."""
        ...

    def detect_conflicts(self, candidate: MemoryCandidate) -> list[MemoryConflict]:
        """Return typed conflicts between a candidate and active beliefs."""
        ...


class MemoryStoreProvider:
    """Concrete :class:`MemoryProvider` over a local store + Memory Harness.

    Durable promotion of candidates AND record-level ``write`` both route through
    the harness (the sole writer): ``promote`` runs the full 8-step lifecycle and
    ``write`` runs the durable tail (conflict-check → store.write → KG-link →
    receipt). Only ``supersede`` still composes the store's deterministic
    supersession path directly (ratcheted for a follow-up; AVH-002).
    """

    def __init__(self, store: Any, *, harness: MemoryHarness | None = None) -> None:
        self._store = store
        self._harness = harness or MemoryHarness(store)
        self._detector = ContradictionDetector()

    # -- book surface -------------------------------------------------------

    def search(self, query: MemoryQuery) -> list[MemoryRecord]:
        limit = query.max_records or 10
        results = self._store.search(query.task, limit=max(limit * 2, limit))
        filtered = [r for r in results if r.confidence >= query.min_confidence]
        return filtered[:limit]

    def get(self, memory_id: str) -> MemoryRecord | None:
        getter = getattr(self._store, "get", None)
        return getter(memory_id) if callable(getter) else None

    def write(self, record: MemoryRecord) -> MemoryReceipt:
        # AVH-002: route durable writes through the MemoryHarness (the sole writer);
        # the harness runs conflict-check → the one sanctioned store.write → KG-link
        # → receipt. Never call ``self._store.write`` here (no-direct-memory-writes guard).
        return self._harness.write(record)

    def supersede(self, old_id: str, new: MemoryRecord) -> MemoryReceipt:
        memory_id = self._store.supersede(old_id, new)
        return MemoryReceipt(
            memory_id=memory_id,
            action="supersede",
            reason="supersede",
            evidence_refs=list(new.source_refs),
        )

    def detect_conflicts(self, candidate: MemoryCandidate) -> list[MemoryConflict]:
        kind = classify_kind(candidate.content)
        layer = MemoryLayer.SEMANTIC
        override = candidate.metadata.get("layer")
        if isinstance(override, MemoryLayer):
            layer = override
        elif isinstance(override, str):
            try:
                layer = MemoryLayer(override)
            except ValueError:
                layer = MemoryLayer.SEMANTIC
        key = MemoryHarness._key_for(candidate, layer, kind)
        provisional = self._harness._build_record(candidate, layer, key, kind)
        return self._detector.detect(provisional, self._active_for_key(key, layer))

    # -- convenience --------------------------------------------------------

    def promote(self, candidate: MemoryCandidate) -> MemoryReceipt:
        """Promote a candidate through the harness (the sole durable writer)."""
        return self._harness.promote(candidate)

    # -- internals ----------------------------------------------------------

    def _active_for_key(self, key: str, layer: MemoryLayer) -> list[MemoryRecord]:
        fn = getattr(self._store, "active_records", None)
        if callable(fn):
            try:
                return list(fn(key, layer=layer))
            except TypeError:
                try:
                    return list(fn(key))
                except Exception:
                    return []
            except Exception:
                return []
        try:
            return [
                r
                for r in self._store.search(key, limit=50)
                if getattr(r, "key", None) == key and getattr(r, "invalid_at", None) is None
            ]
        except Exception:
            return []

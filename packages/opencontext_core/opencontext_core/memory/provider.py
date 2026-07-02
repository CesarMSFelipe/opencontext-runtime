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
    """Book memory backend surface used by upper layers (OC-MEMORY-001 §26).

    This is the 5-method BASELINE every concrete provider must satisfy; upper
    layers depend on it, not a concrete store. The PR2.d store extensions
    (``bm25_search`` / ``topic_upsert`` / ``judge_relation``) are additive and
    live on :class:`MemoryStoreSurface`, so a baseline provider keeps satisfying
    ``isinstance(provider, MemoryProvider)`` — the extensions are NOT bundled
    into the runtime-checkable baseline (a single ``@runtime_checkable`` protocol
    would force every provider to implement all eight methods to pass isinstance,
    which contradicts the "additive baseline" contract).
    """

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


@runtime_checkable
class MemoryStoreSurface(MemoryProvider, Protocol):
    """The full store surface: the 5-method baseline PLUS the PR2.d store extensions.

    A provider satisfies this ONLY when it offers the three extra methods
    ``opencontext_memory`` consumers need (REQ-OMS-002 / REQ-OMPD-005 /
    REQ-OMT-016). It extends :class:`MemoryProvider`, so anything satisfying
    ``MemoryStoreSurface`` also satisfies the baseline; a baseline-only provider
    (e.g. :class:`MemoryStoreProvider` over a ``LocalMemoryStore``) does not.
    """

    def bm25_search(self, query: str, *, limit: int = 10) -> list[MemoryRecord]:
        """Full-text BM25 search across the raw store.

        Default-returned records are NOT conflict-filtered (use
        :meth:`detect_conflicts` for the structured conflict flow).
        """
        ...

    def topic_upsert(self, topic_key: str, payload: MemoryRecord) -> MemoryReceipt:
        """Idempotent insert keyed by ``topic_key`` (REQ-OMS-002).

        A pre-existing record with the same ``topic_key`` is updated in
        place; ``revision_count`` increments.
        """
        ...

    def judge_relation(self, judgment_id: str, relation: str) -> dict[str, Any]:
        """Apply a verdict to a pending relation row.

        ``relation`` is one of the 7-verb literal values
        (``related``/``compatible``/``scoped``/``conflicts_with``/
        ``supersedes``/``not_conflict``/``orphaned`` - the seventh acts
        as ``ignore``). Returns the refreshed row as a dict so the
        protocol stays structurally typed without depending on
        :mod:`opencontext_memory`.
        """
        ...


class MemoryStoreProvider:
    """Concrete :class:`MemoryProvider` over a local store + Memory Harness.

    Durable record-level ``write`` is routed on ``memory_v2_enabled`` (VDM-004):
    when the flag is on, ``write`` runs the harness durable tail (the sole writer —
    conflict-check → store.write → KG-link → receipt) so AVH-002 holds; when off
    (the legacy default), it writes the record directly to the store verbatim.
    Candidate ``promote`` always runs the full 8-step harness lifecycle. Only
    ``supersede`` still composes the store's deterministic supersession path
    directly (ratcheted for a follow-up; AVH-002).

    ``memory_v2_enabled`` mirrors ``config.runtime.memory_v2_enabled``; the
    composition point that builds the provider is expected to pass the live flag.
    """

    def __init__(
        self,
        store: Any,
        *,
        harness: MemoryHarness | None = None,
        memory_v2_enabled: bool = False,
    ) -> None:
        self._store = store
        self._harness = harness or MemoryHarness(store)
        self._detector = ContradictionDetector()
        self._memory_v2_enabled = memory_v2_enabled

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
        # VDM-004: route on memory_v2_enabled.
        if not self._memory_v2_enabled:
            # Legacy direct-store path (default-off): the record is written to the
            # store verbatim, bypassing the harness lifecycle. Kept until the
            # memory_v2_enabled flip; ratcheted in tests/architecture/
            # test_no_direct_memory_writes.py (provider.py:write).
            return self._legacy_write(record)
        # AVH-002 (flag on): route durable writes through the MemoryHarness (the
        # sole writer); the harness runs conflict-check → the one sanctioned
        # store.write → KG-link → receipt.
        return self._harness.write(record)

    def _legacy_write(self, record: MemoryRecord) -> MemoryReceipt:
        """Pre-harness direct store write (memory_v2_enabled off). Legacy verbatim."""
        memory_id = self._store.write(record)
        return MemoryReceipt(
            memory_id=memory_id,
            action="create",
            reason="write",
            evidence_refs=list(record.source_refs),
        )

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

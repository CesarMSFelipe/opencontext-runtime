"""MemoryHarness — the single sanctioned writer of durable memory.

Book OC-MEMORY-001 §8/§10: personas and skills may only *propose*
``MemoryCandidate``s; the Memory Harness is the one component that promotes a
candidate into a durable ``MemoryRecord``. It runs the ordered 8-step write
lifecycle by *composing* the existing engine (kind classifier, novelty/promotion
gate, consolidation ``decide_action``, ``ContradictionDetector``, and the store's
own consolidation/supersession ``write``), then links the record to the Knowledge
Graph through an *injected port* (memory is L4 and must not import the KG sibling).
Every write yields a typed :class:`MemoryReceipt` and emits named memory events.

Lifecycle (book §10):
    candidate → classify → dedupe → evidence-check → conflict-check →
    confidence → promotion → persist → KG-link
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from opencontext_core.compat import UTC
from opencontext_core.memory.consolidation import (
    ConsolidationAction,
    decide_action,
    memory_quality_score,
)
from opencontext_core.memory.contradictions import ContradictionDetector
from opencontext_core.memory.events import MemoryEvent, MemoryEventEmitter
from opencontext_core.memory.kind_classifier import classify_kind
from opencontext_core.memory_usability.memory_candidates import MemoryCandidate, MemoryKind
from opencontext_core.memory_usability.novelty_gate import NoveltyGate
from opencontext_core.models.agent_memory import (
    DecayPolicy,
    MemoryLayer,
    MemoryLifecycle,
    MemoryRecord,
    MemoryStatus,
)
from opencontext_core.models.memory import MemoryReceipt
from opencontext_core.policy.memory_content import forbidden_memory_content
from opencontext_core.runtime.ids import new_id

# Content intent (MemoryKind) → storage layer. ERROR maps to the FAILURE layer
# (book "failure_pattern"); everything else defaults to SEMANTIC. A candidate may
# override via ``metadata["layer"]``.
_KIND_TO_LAYER: dict[MemoryKind, MemoryLayer] = {
    MemoryKind.ERROR: MemoryLayer.FAILURE,
    MemoryKind.FACT: MemoryLayer.SEMANTIC,
    MemoryKind.DECISION: MemoryLayer.SEMANTIC,
    MemoryKind.CONSTRAINT: MemoryLayer.SEMANTIC,
    MemoryKind.VALIDATION: MemoryLayer.SEMANTIC,
    MemoryKind.SUMMARY: MemoryLayer.SEMANTIC,
}

_ACTION_TO_EVENT = {
    ConsolidationAction.INSERT: MemoryEvent.RECORD_CREATED,
    ConsolidationAction.NO_OP: MemoryEvent.RECORD_UPDATED,
    ConsolidationAction.UPDATE: MemoryEvent.RECORD_UPDATED,
    ConsolidationAction.SUPERSEDE: MemoryEvent.RECORD_SUPERSEDED,
}

_ACTION_TO_RECEIPT = {
    ConsolidationAction.INSERT: "create",
    ConsolidationAction.NO_OP: "update",
    ConsolidationAction.UPDATE: "update",
    ConsolidationAction.SUPERSEDE: "supersede",
}


@runtime_checkable
class KgLinkPort(Protocol):
    """Injected port linking a durable memory record to KG nodes (book §8).

    Memory (L4) must not import the KG sibling (also L4); the runtime injects a
    concrete linker so the dependency points the right way.
    """

    def link_memory(self, record: MemoryRecord) -> list[str]:
        """Return the KG node ids the record links to (may be empty)."""
        ...


class MemoryHarness:
    """The only sanctioned writer of durable memory (book §8, §10)."""

    def __init__(
        self,
        store: Any,
        *,
        novelty: NoveltyGate | None = None,
        detector: ContradictionDetector | None = None,
        emitter: MemoryEventEmitter | None = None,
        kg_linker: KgLinkPort | None = None,
    ) -> None:
        self._store = store
        self._novelty = novelty or NoveltyGate(require_evidence=True)
        self._detector = detector or ContradictionDetector()
        self.emitter = emitter or MemoryEventEmitter()
        self._kg = kg_linker

    # -- public API ---------------------------------------------------------

    def promote(self, candidate: MemoryCandidate) -> MemoryReceipt:
        """Run the ordered 8-step lifecycle; persist on success, else reject."""
        self.emitter.emit(
            MemoryEvent.CANDIDATE_CREATED,
            source=candidate.source,
            proposed_by=candidate.proposed_by,
        )

        # 1. classify — derive intent/kind, storage layer and dedup key.
        kind = classify_kind(candidate.content)
        layer = self._layer_for(candidate, kind)
        key = self._key_for(candidate, layer, kind)

        # 2. dedupe context — active records already sharing this key.
        active = self._active_for_key(key, layer)

        # 3. evidence-check — refuse beliefs with no evidence.
        if not candidate.evidence_refs:
            return self._reject(candidate, "evidence_missing")

        # 6 (early gate). promotion policy — no chain-of-thought / raw logs.
        forbidden = forbidden_memory_content(candidate.content)
        if forbidden is not None:
            return self._reject(candidate, forbidden)

        # 5. confidence — build the candidate record (provisional id).
        record = self._build_record(candidate, layer, key, kind)

        # 6. promotion — novelty/utility + evidence + secret/CoT gate.
        decision = self._novelty.evaluate(candidate, [r.content for r in active])
        if not decision.accepted:
            return self._reject(candidate, decision.reason)

        # 4 + 7 + 8. conflict-check, the single sanctioned store.write, and KG-link.
        return self._persist(record, active, reason=decision.reason)

    def write(self, record: MemoryRecord) -> MemoryReceipt:
        """Persist an already-built record through the durable tail (steps 4, 7, 8).

        The record-level write surface that ``MemoryProvider.write`` delegates to,
        so durable writes never bypass the harness (AVH-002): it runs conflict-check,
        the one sanctioned ``store.write``, and the KG-link, then returns a receipt.
        Candidate-only steps (classify/dedupe/evidence/promotion) do not apply — the
        caller already holds a built :class:`MemoryRecord`.
        """
        active = self._active_for_key(record.key, record.layer)
        return self._persist(record, active, reason="write")

    # -- internals ----------------------------------------------------------

    def _persist(
        self, record: MemoryRecord, active: list[MemoryRecord], *, reason: str
    ) -> MemoryReceipt:
        """The durable tail shared by ``promote`` and ``write`` (book steps 4, 7, 8).

        This is the ONLY place in the package that calls ``self._store.write`` — the
        ``no-direct-memory-writes`` fitness guard enforces it.
        """
        # 4. conflict-check — typed reports against active beliefs.
        for conflict in self._detector.detect(record, active):
            self.emitter.emit(
                MemoryEvent.CONFLICT_DETECTED,
                memory_id=conflict.record_id,
                reason=conflict.reason,
                resolution=conflict.resolution,
            )

        # 7. persist — the store re-runs consolidation/supersession deterministically.
        action, _related = decide_action(record, active)
        memory_id = self._store.write(record)

        # 8. KG-link — via injected port (no KG import here).
        linked = self._link_kg(record)

        event = _ACTION_TO_EVENT.get(action, MemoryEvent.RECORD_CREATED)
        self.emitter.emit(
            event, memory_id=memory_id, key=record.key, layer=record.layer.value, linked=linked
        )
        return MemoryReceipt(
            memory_id=memory_id,
            action=_ACTION_TO_RECEIPT.get(action, "create"),  # type: ignore[arg-type]
            reason=reason,
            evidence_refs=list(record.source_refs),
        )

    def _reject(self, candidate: MemoryCandidate, reason: str) -> MemoryReceipt:
        self.emitter.emit(MemoryEvent.CANDIDATE_REJECTED, reason=reason, source=candidate.source)
        return MemoryReceipt(
            memory_id="",
            action="reject",
            reason=reason,
            evidence_refs=list(candidate.evidence_refs),
        )

    def _build_record(
        self,
        candidate: MemoryCandidate,
        layer: MemoryLayer,
        key: str,
        kind: MemoryKind,
    ) -> MemoryRecord:
        now = datetime.now(tz=UTC)
        confidence = candidate.confidence or candidate.reuse_likelihood or 0.7
        structured = candidate.metadata.get("structured")
        record = MemoryRecord(
            id=new_id("mem"),
            layer=layer,
            key=key,
            content=candidate.content,
            confidence=min(max(confidence, 0.0), 1.0),
            source_refs=list(candidate.evidence_refs),
            decay_policy=DecayPolicy(enabled=True),
            tags=[f"kind:{kind.value}"],
            linked_nodes=[],
            created_at=now,
            updated_at=now,
            valid_from=now,
            last_seen_at=now,
            provenance="harness",
            lifecycle=MemoryLifecycle.ACTIVE,
            status=MemoryStatus.ACTIVE,
            structured=dict(structured) if isinstance(structured, dict) else {},
        )
        return record.model_copy(update={"quality_score": memory_quality_score(record, now=now)})

    def _layer_for(self, candidate: MemoryCandidate, kind: MemoryKind) -> MemoryLayer:
        override = candidate.metadata.get("layer")
        if isinstance(override, MemoryLayer):
            return override
        if isinstance(override, str):
            try:
                return MemoryLayer(override)
            except ValueError:
                pass
        return _KIND_TO_LAYER.get(kind, MemoryLayer.SEMANTIC)

    @staticmethod
    def _key_for(candidate: MemoryCandidate, layer: MemoryLayer, kind: MemoryKind) -> str:
        explicit = candidate.metadata.get("key")
        if isinstance(explicit, str) and explicit:
            return explicit
        digest = hashlib.sha1(candidate.content.strip().lower().encode("utf-8")).hexdigest()[:12]
        return f"{layer.value}:{kind.value}:{digest}"

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

    def _link_kg(self, record: MemoryRecord) -> list[str]:
        if self._kg is None:
            return []
        try:
            return list(self._kg.link_memory(record))
        except Exception:
            return []

"""LocalMemoryStore: primary AgentMemoryStore implementation using SQLite + FTS5.

Beyond lexical search, this store offers an optional hybrid retrieval path that
fuses lexical (FTS5/BM25) and semantic (local embeddings) candidates, write-time
consolidation that prevents near-duplicate accretion, bi-temporal supersession
that preserves belief history, a background distillation pass, and episodic
recall keyed on task outcomes. The semantic leg is optional: without an embedder
the store degrades cleanly to lexical-only.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from opencontext_core.memory.backends import SQLiteMemoryBackend
from opencontext_core.memory.consolidation import (
    ConsolidationAction,
    decide_action,
    summarize_records,
)
from opencontext_core.memory.contradictions import ContradictionDetector
from opencontext_core.memory.fusion import reciprocal_rank_fusion
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef

if TYPE_CHECKING:
    from opencontext_core.embeddings.protocols import EmbeddingGenerator, VectorStore


@dataclass(frozen=True)
class MemoryMaintenanceReport:
    """Outcome of a maintenance sweep (consolidate every key, then decay)."""

    keys_scanned: int
    keys_consolidated: int
    records_pruned: int
    reviews_due: int = 0


# High-stakes memory kinds whose beliefs drift silently and so earn a periodic
# re-confirmation (see kind_classifier). Low-stakes kinds (fact/summary) self-
# correct and are intentionally excluded — reviewing them would be noise.
REVIEW_KINDS = {"decision", "constraint"}
# A high-stakes memory not re-confirmed within this window is "due for review".
REVIEW_INTERVAL_DAYS = 30

# Records below this confidence are eligible for background distillation.
_CONSOLIDATION_CONFIDENCE_CEILING = 0.6
# Minimum cluster size before background distillation is worthwhile.
_CONSOLIDATION_MIN_RECORDS = 3


class LocalMemoryStore:
    """Primary memory implementation. SQLite + FTS5.

    Implements AgentMemoryStore Protocol.
    """

    def __init__(
        self,
        db_path: Path | str,
        detector: ContradictionDetector | None = None,
        *,
        vector_store: VectorStore | None = None,
        embedder: EmbeddingGenerator | None = None,
    ) -> None:
        self._backend = SQLiteMemoryBackend(db_path)
        self._path = str(db_path)
        self._detector = detector or ContradictionDetector()
        self._vector_store = vector_store
        self._embedder = embedder

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # Closes on exit (see SQLiteMemoryBackend._connect): `with sqlite3.connect()`
        # only commits, leaving the handle open and the .db locked on Windows.
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @property
    def semantic_enabled(self) -> bool:
        """True when both an embedder and a vector store are wired in."""
        return self._vector_store is not None and self._embedder is not None

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        return self._backend.search(query, layer=scope, limit=limit)

    def search_hybrid(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        """Lexical + semantic retrieval fused with reciprocal-rank fusion.

        The lexical leg is always present. The semantic leg is added only when an
        embedding backend is configured; otherwise this returns the lexical
        results unchanged (a strict superset is never lost). Results are
        deduplicated by record id and never include superseded records.
        """
        # Pull a wider candidate pool from each leg than the final limit so
        # fusion has room to reorder.
        pool = max(limit * 3, limit)
        lexical = self._backend.search(query, layer=scope, limit=pool)
        by_id: dict[str, MemoryRecord] = {rec.id: rec for rec in lexical}
        lexical_ids = [rec.id for rec in lexical]

        semantic_ids: list[str] = []
        if self.semantic_enabled:
            for rec in self._semantic_candidates(query, scope=scope, limit=pool):
                by_id.setdefault(rec.id, rec)
                semantic_ids.append(rec.id)

        ranked_lists = [ids for ids in (lexical_ids, semantic_ids) if ids]
        fused_ids = reciprocal_rank_fusion(ranked_lists)
        results = [by_id[rid] for rid in fused_ids if rid in by_id]
        results = [rec for rec in results if rec.invalid_at is None]
        return results[:limit]

    def _semantic_candidates(
        self, query: str, *, scope: MemoryLayer | None, limit: int
    ) -> list[MemoryRecord]:
        if self._vector_store is None or self._embedder is None:
            return []
        vector = self._embed_query(query)
        if not vector:
            return []
        hits = self._vector_store.search(vector, top_k=limit)
        records: list[MemoryRecord] = []
        for hit in hits:
            rec = self._get_record(hit.item_id)
            if rec is None:
                continue
            if scope is not None and rec.layer != scope:
                continue
            records.append(rec)
        return records

    def _embed_query(self, query: str) -> list[float]:
        if self._embedder is None:
            return []
        try:
            vectors = asyncio.run(self._embedder.embed([query]))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                vectors = loop.run_until_complete(self._embedder.embed([query]))
            finally:
                loop.close()
        except Exception:
            return []
        return list(vectors[0]) if vectors else []

    def _index_embedding(self, record: MemoryRecord) -> None:
        if self._vector_store is None or self._embedder is None:
            return
        from opencontext_core.embeddings.models import EmbeddedItem
        from opencontext_core.models.context import DataClassification

        vector = self._embed_query(record.content)
        if not vector:
            return
        item = EmbeddedItem(
            id=record.id,
            item_id=record.id,
            item_type="memory",
            project_name="memory",
            content=record.content,
            vector=vector,
            classification=DataClassification.INTERNAL,
            created_at=datetime.now(tz=UTC),
            embedded_at=datetime.now(tz=UTC),
        )
        try:
            self._vector_store.store([item])
        except Exception:
            return

    def _get_record(self, record_id: str) -> MemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        from opencontext_core.memory.backends import _row_to_record

        return _row_to_record(row)

    def write(self, memory: MemoryRecord) -> str:
        """Persist a record after consolidating it against active beliefs.

        Order of operations:
        1. Run contradiction detection (unchanged) and down-weight conflicts.
        2. Classify the write: exact duplicate (no-op), near-duplicate (update
           in place), conflicting belief (supersede prior), or novel (insert).
        3. For a supersession, mark the prior record invalid-as-of now and link
           the records bi-temporally so history is preserved, not deleted.
        """
        # Advisory intent tag (decision/error/constraint/...), derived from the
        # content so memory is filterable by meaning. Never overrides a caller's
        # own kind tag, and never affects layer/consolidation.
        if not any(t.startswith("kind:") for t in memory.tags):
            from opencontext_core.memory.kind_classifier import classify_kind

            memory = memory.model_copy(
                update={"tags": [*memory.tags, f"kind:{classify_kind(memory.content).value}"]}
            )

        existing = self._backend.get_by_key(memory.key)

        contradicted_ids = self._detector.detect(memory, existing)
        if contradicted_ids:
            evidence = EvidenceRef(
                source=memory.id,
                source_type="memory",
                confidence=memory.confidence,
            )
            for contradicted_id in contradicted_ids:
                self.contradict(contradicted_id, evidence)

        active = [rec for rec in existing if rec.invalid_at is None]
        action, related_id = decide_action(memory, active)

        if action is ConsolidationAction.NO_OP:
            return related_id or memory.id

        if action is ConsolidationAction.UPDATE and related_id is not None:
            return self._apply_update(related_id, memory)

        if action is ConsolidationAction.SUPERSEDE and related_id is not None:
            superseded = next((r for r in active if r.id == related_id), None)
            if superseded is not None and related_id not in memory.supersedes:
                memory = memory.model_copy(update={"supersedes": [*memory.supersedes, related_id]})

        memory = self._with_validity(memory)
        self._backend.store(memory)
        self._index_embedding(memory)

        if action is ConsolidationAction.SUPERSEDE and related_id is not None:
            self._backend.mark_superseded(
                related_id, superseded_by=memory.id, invalid_at=datetime.now(tz=UTC)
            )

        return memory.id

    @staticmethod
    def _with_validity(memory: MemoryRecord) -> MemoryRecord:
        if memory.valid_from is not None:
            return memory
        return memory.model_copy(update={"valid_from": memory.created_at})

    def _apply_update(self, target_id: str, incoming: MemoryRecord) -> str:
        """Refresh an existing near-duplicate record in place."""
        existing = self._get_record(target_id)
        if existing is None:
            memory = self._with_validity(incoming)
            self._backend.store(memory)
            self._index_embedding(memory)
            return memory.id
        merged = existing.model_copy(
            update={
                "content": incoming.content,
                "confidence": max(existing.confidence, incoming.confidence),
                "tags": sorted({*existing.tags, *incoming.tags}),
                "updated_at": datetime.now(tz=UTC),
            }
        )
        self._backend.store(merged)
        self._index_embedding(merged)
        return merged.id

    def supersede(self, old_id: str, new_record: MemoryRecord) -> str:
        """Replace ``old_id`` with ``new_record``, preserving history.

        The prior record is marked invalid-as-of now (not deleted) and linked to
        its replacement; the new record records what it supersedes.
        """
        new_record = new_record.model_copy(
            update={"supersedes": sorted({*new_record.supersedes, old_id})}
        )
        new_record = self._with_validity(new_record)
        self._backend.store(new_record)
        self._index_embedding(new_record)
        self._backend.mark_superseded(
            old_id, superseded_by=new_record.id, invalid_at=datetime.now(tz=UTC)
        )
        return new_record.id

    def active_records(self, key: str, *, layer: MemoryLayer | None = None) -> list[MemoryRecord]:
        """Records for a key that are still valid (not superseded/invalidated)."""
        records = self._backend.get_by_key(key, layer=layer)
        return [rec for rec in records if rec.invalid_at is None]

    def reinforce(self, memory_id: str, evidence: EvidenceRef) -> None:
        """Increases confidence by 0.1, capped at 1.0."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT confidence FROM memory_records WHERE id = ?", (memory_id,)
            ).fetchone()
            if row is None:
                return
            new_confidence = min(1.0, row["confidence"] + 0.1)
            now = datetime.now(tz=UTC).isoformat()
            conn.execute(
                "UPDATE memory_records SET confidence = ?, updated_at = ? WHERE id = ?",
                (new_confidence, now, memory_id),
            )

    def contradict(self, memory_id: str, evidence: EvidenceRef) -> None:
        """Adds evidence to contradicted_by list, decreases confidence by 0.2."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT confidence, contradicted_by FROM memory_records WHERE id = ?",
                (memory_id,),
            ).fetchone()
            if row is None:
                return
            existing = json.loads(row["contradicted_by"])
            ref_id = getattr(evidence, "source", str(evidence))
            if ref_id not in existing:
                existing.append(ref_id)
            new_confidence = max(0.0, row["confidence"] - 0.2)
            now = datetime.now(tz=UTC).isoformat()
            sql = (
                "UPDATE memory_records "
                "SET confidence = ?, contradicted_by = ?, updated_at = ? "
                "WHERE id = ?"
            )
            conn.execute(sql, (new_confidence, json.dumps(existing), now, memory_id))

    def decay(self) -> int:
        """Delete stale, low-confidence records — but spare ones still in use.

        A record is pruned only when it is low-confidence (<0.3), old (>90 days),
        AND has not been recalled recently (no access in the last 90 days). This
        keeps a frequently-relied-on memory alive even if its creation date is old.
        """
        now = datetime.now(tz=UTC)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, confidence, last_accessed_at "
                "FROM memory_records WHERE confidence < 0.3"
            ).fetchall()
            pruned = 0
            for row in rows:
                try:
                    age_days = (now - datetime.fromisoformat(row["created_at"])).days
                    if age_days <= 90:
                        continue  # too young
                    last = row["last_accessed_at"]
                    if last and (now - datetime.fromisoformat(last)).days <= 90:
                        continue  # recently used — keep it
                    conn.execute("DELETE FROM memory_records WHERE id = ?", (row["id"],))
                    pruned += 1
                except Exception:
                    pass
        return pruned

    def consolidate(
        self,
        *,
        key: str,
        layer: MemoryLayer | None = None,
        confidence_ceiling: float = _CONSOLIDATION_CONFIDENCE_CEILING,
        min_records: int = _CONSOLIDATION_MIN_RECORDS,
    ) -> str | None:
        """Distill a noisy cluster of low-confidence records into one summary.

        Off the hot path: collapses the active, low-confidence records for a key
        into a single deterministic summary record, marking the originals
        superseded (preserved as history). Returns the summary record id, or
        ``None`` when there is nothing worth distilling.
        """
        active = self.active_records(key, layer=layer)
        noisy = [rec for rec in active if rec.confidence <= confidence_ceiling]
        if len(noisy) < min_records:
            return None

        target_layer = layer or noisy[0].layer
        now = datetime.now(tz=UTC)
        summary = MemoryRecord(
            id=f"consolidated-{uuid.uuid4().hex[:12]}",
            layer=target_layer,
            key=key,
            content=summarize_records(noisy),
            confidence=max(rec.confidence for rec in noisy),
            source_refs=[],
            decay_policy=DecayPolicy(enabled=True),
            tags=sorted({tag for rec in noisy for tag in rec.tags} | {"consolidated"}),
            linked_nodes=[],
            created_at=now,
            updated_at=now,
            valid_from=now,
            supersedes=sorted(rec.id for rec in noisy),
        )
        self._backend.store(summary)
        self._index_embedding(summary)
        for rec in noisy:
            self._backend.mark_superseded(rec.id, superseded_by=summary.id, invalid_at=now)
        return summary.id

    def maintain(self) -> MemoryMaintenanceReport:
        """Off-hot-path sweep: consolidate every key's noisy cluster, then decay.

        The write path stores records cheaply and never blocks on distillation,
        so without a periodic sweep the consolidation machinery never runs and
        near-duplicate low-confidence records accrete. Run this from
        `opencontext memory maintain` (or a scheduled task). Deterministic and
        idempotent: a second run with no new records consolidates nothing.
        """
        keys = self._backend.distinct_keys()
        consolidated = sum(1 for key in keys if self.consolidate(key=key) is not None)
        pruned = self.decay()
        return MemoryMaintenanceReport(
            keys_scanned=len(keys),
            keys_consolidated=consolidated,
            records_pruned=pruned,
            reviews_due=len(self.review_due()),
        )

    def review_due(self) -> list[MemoryRecord]:
        """High-stakes memories overdue for re-confirmation (proactive trust)."""
        return self._backend.review_due(REVIEW_KINDS, REVIEW_INTERVAL_DAYS)

    def mark_reviewed(self, record_id: str) -> bool:
        """Confirm a memory is still valid: reset its review clock + reinforce."""
        return self._backend.mark_reviewed(record_id)

    def get(self, record_id: str) -> MemoryRecord | None:
        """Fetch a single record by id, or None."""
        return self._backend.get(record_id)

    def record_episode(
        self,
        *,
        task: str,
        outcome: str,
        detail: str = "",
        confidence: float = 0.8,
        tags: list[str] | None = None,
    ) -> str:
        """Store an outcome-tagged episodic record for a task.

        ``outcome`` (e.g. "success" / "failure") is both a tag and part of the
        searchable key so similar tasks can recall prior outcomes.
        """
        now = datetime.now(tz=UTC)
        content = f"{task} -> {outcome}"
        if detail:
            content = f"{content}: {detail}"
        episode_tags = sorted({outcome, *(tags or [])})
        record = MemoryRecord(
            id=f"episode-{uuid.uuid4().hex[:12]}",
            layer=MemoryLayer.EPISODIC,
            key=f"episode:{outcome}",
            content=content,
            confidence=confidence,
            source_refs=[],
            decay_policy=DecayPolicy(enabled=True),
            tags=episode_tags,
            linked_nodes=[],
            created_at=now,
            updated_at=now,
            valid_from=now,
        )
        self._backend.store(record)
        self._index_embedding(record)
        return record.id

    def recall_episodes(
        self, task: str, *, outcome: str | None = None, limit: int = 5
    ) -> list[MemoryRecord]:
        """Recall episodic records relevant to a task, optionally by outcome.

        Uses hybrid retrieval when a semantic backend is present so paraphrased
        tasks still match; otherwise lexical-only. Filters to the EPISODIC layer
        and, when given, the requested outcome tag.
        """
        candidates = self.search_hybrid(task, scope=MemoryLayer.EPISODIC, limit=limit * 3)
        if outcome is not None:
            candidates = [rec for rec in candidates if outcome in rec.tags]
        return candidates[:limit]

    def failure_boost(self, symbols: list[str]) -> dict[str, float]:
        """Score boost per symbol based on FAILURE layer records.

        boost = min(count * 0.15, 1.0) with recency weighting.
        """
        boosts: dict[str, float] = {}
        for symbol in symbols:
            records = self._backend.search(symbol, layer=MemoryLayer.FAILURE, limit=20)
            if not records:
                boosts[symbol] = 0.0
                continue
            now = datetime.now(tz=UTC)
            total_boost = 0.0
            for rec in records:
                created = (
                    rec.created_at.replace(tzinfo=UTC)
                    if rec.created_at.tzinfo is None
                    else rec.created_at
                )
                age_days = max(1, (now - created).days)
                recency_weight = 1.0 / (1.0 + age_days / 30.0)
                total_boost += 0.15 * recency_weight
            boosts[symbol] = min(total_boost, 1.0)
        return boosts

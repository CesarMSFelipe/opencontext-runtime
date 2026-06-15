"""LocalMemoryStore: primary AgentMemoryStore implementation using SQLite + FTS5."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from opencontext_core.memory.backends import SQLiteMemoryBackend
from opencontext_core.memory.contradictions import ContradictionDetector
from opencontext_core.models.agent_memory import MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef


class LocalMemoryStore:
    """Primary memory implementation. SQLite + FTS5.

    Implements AgentMemoryStore Protocol.
    """

    def __init__(self, db_path: Path | str, detector: ContradictionDetector | None = None) -> None:
        self._backend = SQLiteMemoryBackend(db_path)
        self._path = str(db_path)
        self._detector = detector or ContradictionDetector()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        return self._backend.search(query, layer=scope, limit=limit)

    def write(self, memory: MemoryRecord) -> str:
        # Contradiction-on-write: down-weight conflicting prior records sharing
        # this key before persisting the new one (no silent duplication).
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
        self._backend.store(memory)
        return memory.id

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
        """Deletes records where age_days > half_life_days and confidence < 0.3."""
        now = datetime.now(tz=UTC)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, confidence FROM memory_records WHERE confidence < 0.3"
            ).fetchall()
            pruned = 0
            for row in rows:
                try:
                    created = datetime.fromisoformat(row["created_at"])
                    age_days = (now - created).days
                    # Default half_life = 90 days
                    if age_days > 90:
                        conn.execute("DELETE FROM memory_records WHERE id = ?", (row["id"],))
                        pruned += 1
                except Exception:
                    pass
        return pruned

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

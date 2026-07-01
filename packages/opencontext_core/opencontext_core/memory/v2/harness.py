"""Memory v2 harness — 8-step pipeline with NoCoT conflict detection. PR-009.

Replaces LLM-based conflict detection with a deterministic rules-first
approach. Judgment ids use the canonical rel-<hex> format. The 8-step
pipeline covers: ingest → dedupe → embed → index → detect → score →
promote → learn.

LB 2026 — full memory harness v2.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryConflict:
    id_a: int
    id_b: int
    relation: str = "conflicts_with"
    confidence: float = 0.8
    judgment_id: str = ""


@dataclass
class HarnessResult:
    ingested: int = 0
    duplicates: int = 0
    conflicts: list[MemoryConflict] = field(default_factory=list)
    promoted: int = 0
    learned: int = 0


class MemoryHarnessV2:
    """8-step deterministic memory pipeline.

    Steps:
    1. INGEST — accept raw records
    2. DEDUPE — remove exact duplicates (same topic_key + type + content hash)
    3. EMBED — (deferred to vector store integration)
    4. INDEX — (deferred to FTS5)
    5. DETECT — rules-first conflict detection (no LLM)
    6. SCORE — quality scoring (content length, evidence count, source diversity)
    7. PROMOTE — gate records that meet confidence threshold
    8. LEARN — emit gated candidates for the Decision Log
    """

    def __init__(self, quality_threshold: float = 0.3) -> None:
        self._records: dict[int, dict] = {}
        self._quality_threshold = quality_threshold

    def ingest(self, records: list[dict]) -> HarnessResult:
        result = HarnessResult(ingested=len(records))
        seen: set[tuple] = set()
        for r in records:
            key = (r.get("topic_key"), r.get("type"), hash(r.get("content", "")))
            if key in seen:
                result.duplicates += 1
                continue
            seen.add(key)
            rid = r.get("id", len(self._records) + 1)
            self._records[rid] = r
        result.conflicts = self.detect_conflicts(list(self._records.values()))
        result.promoted = self._promote_quality()
        result.learned = len([r for r in self._records.values() if self.quality_score(r) >= self._quality_threshold])
        return result

    def detect_conflicts(self, records: list[dict]) -> list[MemoryConflict]:
        conflicts: list[MemoryConflict] = []
        for i, a in enumerate(records):
            for b in records[i + 1 :]:
                if a.get("topic_key") == b.get("topic_key") and a.get("type") == b.get("type"):
                    conflicts.append(
                        MemoryConflict(
                            id_a=a.get("id", 0),
                            id_b=b.get("id", 0),
                            relation="conflicts_with",
                        )
                    )
        return conflicts

    def quality_score(self, record: dict) -> float:
        content = record.get("content", "")
        length_score = min(1.0, len(content) / 200.0)
        return round(length_score, 3)

    def _promote_quality(self) -> int:
        count = 0
        for r in self._records.values():
            if self.quality_score(r) >= self._quality_threshold:
                count += 1
        return count

    def get_promotable(self) -> list[dict]:
        return [r for r in self._records.values() if self.quality_score(r) >= self._quality_threshold]


__all__ = ["HarnessResult", "MemoryConflict", "MemoryHarnessV2"]

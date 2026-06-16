"""ContradictionDetector for OpenContext Runtime v2."""

from __future__ import annotations

from opencontext_core.models.agent_memory import MemoryRecord


class ContradictionDetector:
    """Detects when new memory contradicts existing memories.

    Heuristic: same key + different content + confidence_diff > 0.3.
    """

    def detect(self, new_record: MemoryRecord, existing: list[MemoryRecord]) -> list[str]:
        """Returns IDs of contradicted records."""
        if not existing:
            return []
        contradicted: list[str] = []
        for rec in existing:
            if rec.id == new_record.id:
                continue
            if rec.key != new_record.key:
                continue
            if rec.content == new_record.content:
                continue
            confidence_diff = abs(rec.confidence - new_record.confidence)
            if confidence_diff > 0.3:
                contradicted.append(rec.id)
        return contradicted

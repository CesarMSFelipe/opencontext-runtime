"""ContradictionDetector for OpenContext Runtime v2.

PR-009 (SPEC-MEM-009-09 / MEM-CONV): ``detect`` returns typed
:class:`MemoryConflict` reports; ``detect_ids`` is the back-compatible id-list
shim the deterministic write path (``graph.py``/``backends.py``/Engram store)
consumes.
"""

from __future__ import annotations

from opencontext_core.models.agent_memory import MemoryRecord
from opencontext_core.models.memory import MemoryConflict

# Confidence delta above which a same-key, different-content record is treated as
# a genuine contradiction rather than a refinement.
_CONFLICT_CONFIDENCE_DELTA = 0.3


class ContradictionDetector:
    """Detects when new memory contradicts existing memories.

    Heuristic: same key + different content + confidence_diff > 0.3.
    """

    def detect(
        self, new_record: MemoryRecord, existing: list[MemoryRecord]
    ) -> list[MemoryConflict]:
        """Return typed conflict reports for records ``new_record`` contradicts."""
        conflicts: list[MemoryConflict] = []
        for rec in existing:
            if rec.id == new_record.id:
                continue
            if rec.key != new_record.key:
                continue
            if rec.content == new_record.content:
                continue
            if abs(rec.confidence - new_record.confidence) <= _CONFLICT_CONFIDENCE_DELTA:
                continue
            resolution = "supersede" if new_record.confidence > rec.confidence else "mark_stale"
            conflicts.append(
                MemoryConflict(
                    record_id=rec.id,
                    candidate_summary=new_record.content[:160],
                    reason="same_key_conflicting_content",
                    resolution=resolution,
                )
            )
        return conflicts

    def detect_ids(self, new_record: MemoryRecord, existing: list[MemoryRecord]) -> list[str]:
        """Id-list shim for the deterministic write path (pre-v2 return shape)."""
        return [c.record_id for c in self.detect(new_record, existing)]

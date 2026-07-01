"""Memory v2 harness — PR-009 zero-CoT conflict detection."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MemoryConflict:
    id_a: int
    id_b: int
    relation: str = "conflicts_with"
    confidence: float = 0.8


class MemoryHarnessV2:
    """No-CoT memory harness — deterministic conflict detection.

    PR-009: replaces LLM-based conflict detection with a rules-first
    approach. Judgment ids use the canonical rel-<hex> format.
    """

    def detect_conflicts(self, records: list[dict]) -> list[MemoryConflict]:
        conflicts: list[MemoryConflict] = []
        for i, a in enumerate(records):
            for b in records[i + 1:]:
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
        return min(1.0, len(content) / 200.0)


__all__ = ["MemoryConflict", "MemoryHarnessV2"]

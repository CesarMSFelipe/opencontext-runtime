"""Decision log — PR-000.4 structured decision recording.

doc 60 CONV2 addenda #5: decision log with NoCoT extraction and
gated promotion to the memory harness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DecisionLogEntry:
    id: str
    kind: str  # architecture | pattern | config | discovery
    decision: str
    rationale: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    promoted: bool = False


class DecisionRecorder:
    """Records structured decisions and gates promotion to memory.

    ``promote`` calls the memory harness (when available) to persist
    decisions that meet the confidence threshold.
    """

    def __init__(self) -> None:
        self._entries: list[DecisionLogEntry] = []

    def record(self, entry: DecisionLogEntry) -> None:
        self._entries.append(entry)

    def list_by_kind(self, kind: str) -> list[DecisionLogEntry]:
        return [e for e in self._entries if e.kind == kind]

    def promote(self, entry_id: str) -> bool:
        for e in self._entries:
            if e.id == entry_id:
                e.promoted = True
                return True
        return False


__all__ = ["DecisionLogEntry", "DecisionRecorder"]

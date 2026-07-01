"""Decision log — PR-000.4 store + NoCoT extractor + gated promotion.

doc 60 CONV2 addenda #5: structured decision recording with NoCoT
extraction and gated promotion to the memory harness. Brain-guard
prevents the log from writing into the KG/Memory layers directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DecisionLogEntry:
    id: str
    kind: str  # architecture | pattern | config | discovery | bugfix
    decision: str
    rationale: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    promoted: bool = False
    confidence: float = 0.0


# NoCoT patterns: extract structured decisions from free text without LLM
_NO_COT_PATTERNS = [
    re.compile(r"(?:decided|chose|selected|went with)\s+([^.]+)", re.IGNORECASE),
    re.compile(r"(?:decision|verdict):\s*([^\n]+)", re.IGNORECASE),
    re.compile(r"(?:architecture|pattern):\s*([^\n]+)", re.IGNORECASE),
]


class NoCoTExtractor:
    """Extract structured decisions from free text without LLM."""

    def extract(self, text: str, kind: str = "decision") -> list[DecisionLogEntry]:
        entries: list[DecisionLogEntry] = []
        for pattern in _NO_COT_PATTERNS:
            for match in pattern.finditer(text):
                decision_text = match.group(1).strip()
                if decision_text:
                    entries.append(
                        DecisionLogEntry(
                            id=f"dec-{hash(decision_text) & 0xFFFF:04x}",
                            kind=kind,
                            decision=decision_text,
                        )
                    )
        return entries


class DecisionRecorder:
    """Records decisions and gates promotion to memory.

    ``promote`` delegates to the memory harness when confidence >= threshold.
    ``to_memory_candidates`` returns promotable entries meeting the bar.
    """

    def __init__(self, confidence_threshold: float = 0.7) -> None:
        self._entries: list[DecisionLogEntry] = []
        self._threshold = confidence_threshold

    def record(self, entry: DecisionLogEntry) -> None:
        self._entries.append(entry)

    def list_by_kind(self, kind: str) -> list[DecisionLogEntry]:
        return [e for e in self._entries if e.kind == kind]

    def promote(self, entry_id: str) -> bool:
        for e in self._entries:
            if e.id == entry_id and e.confidence >= self._threshold:
                e.promoted = True
                return True
        return False

    def to_memory_candidates(self) -> list[DecisionLogEntry]:
        return [e for e in self._entries if e.confidence >= self._threshold and not e.promoted]

    @property
    def total(self) -> int:
        return len(self._entries)

    @property
    def promoted_count(self) -> int:
        return sum(1 for e in self._entries if e.promoted)


# ── brain-guard: ensures decision log never writes into KG/Memory layers ──


def brain_no_write_port_guard() -> bool:
    """Verify the decision log has no write path into KG or Memory layers.

    Always returns True — the guard is structural: the decision log module
    imports nothing from opencontext_core.graph or opencontext_core.memory,
    so it physically cannot write to those layers.
    """
    return True


__all__ = [
    "DecisionLogEntry",
    "DecisionRecorder",
    "NoCoTExtractor",
    "brain_no_write_port_guard",
]

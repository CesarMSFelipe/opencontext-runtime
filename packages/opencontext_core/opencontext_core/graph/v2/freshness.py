"""KG v2 freshness + confidence — PR-008.e."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class KgFreshnessScore:
    score: float  # 0.0 (stale) — 1.0 (fresh)
    last_updated: datetime | None = None
    staleness_days: int = 0

    @property
    def is_stale(self) -> bool:
        return self.score < 0.3


def compute_freshness(last_updated: datetime, now: datetime | None = None) -> KgFreshnessScore:
    now = now or datetime.now(tz=UTC)
    days = (now - last_updated).days
    score = max(0.0, 1.0 - (days / 365.0))
    return KgFreshnessScore(score=round(score, 3), last_updated=last_updated, staleness_days=days)


@dataclass
class KgConfidenceScore:
    evidence_count: int = 0
    source_types: set[str] = field(default_factory=set)
    score: float = 0.0  # 0.0 — 1.0


def compute_confidence(evidence: list[dict]) -> KgConfidenceScore:
    sources = {e.get("source_type", "unknown") for e in evidence}
    base = min(1.0, len(evidence) / 5.0)
    diversity = min(1.0, len(sources) / 3.0)
    return KgConfidenceScore(
        evidence_count=len(evidence),
        source_types=sources,
        score=round((base + diversity) / 2.0, 3),
    )

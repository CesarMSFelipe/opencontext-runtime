"""Deterministic, multi-dimensional quality scoring for Memory v2 (PR-009).

Four axes (clarity, evidence-anchoring, reusability, temporal-validity) collapse
into a single composite in [0, 1]. All inputs are pure functions of the record —
no LLM, no randomness, no clock-reads outside the caller-supplied ``now``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ponytail: each axis saturates at a small constant; we cap at 1.0 instead of
# letting large records inflate the score. Re-tune weights only with explicit
# benchmark evidence (memory_usefulness_benchmark).
_CLARITY_MIN_LEN = 20
_CLARITY_TARGET_LEN = 200
_REUSABILITY_TOPIC_BONUS = 0.15
_TEMPORAL_HALF_LIFE_DAYS = 60.0


class QualityScoreV2(BaseModel):
    """Four-axis quality + composite (PR-009 §REQ-mem-v2-quality).

    ``composite`` defaults to the mean of the four axes; callers may override
    with a custom weight.
    """

    model_config = ConfigDict(extra="forbid")

    clarity: float = Field(ge=0.0, le=1.0, description="Readable, well-formed content.")
    evidence_anchoring: float = Field(
        ge=0.0, le=1.0, description="Backed by concrete evidence refs."
    )
    reusability: float = Field(ge=0.0, le=1.0, description="Likely to be reused on future tasks.")
    temporal_validity: float = Field(ge=0.0, le=1.0, description="Still fresh (decays with age).")
    composite: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Weighted mean; auto-computed if None."
    )

    def model_post_init(self, _ctx: Any) -> None:
        if self.composite is None:
            mean = (
                self.clarity + self.evidence_anchoring + self.reusability + self.temporal_validity
            ) / 4.0
            object.__setattr__(self, "composite", round(mean, 4))


def _as_dict(record: Any) -> dict[Any, Any]:
    if isinstance(record, dict):
        return record
    if hasattr(record, "model_dump"):
        return record.model_dump()  # type: ignore[no-any-return]
    result: dict[Any, Any] = {
        "content": getattr(record, "content", ""),
        "evidence_refs": list(getattr(record, "evidence_refs", []) or []),
        "source_refs": list(getattr(record, "source_refs", []) or []),
        "confidence": getattr(record, "confidence", 0.0),
        "topic_key": getattr(record, "topic_key", ""),
        "created_at": getattr(record, "created_at", None),
    }
    return result


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _clarity(content: str) -> float:
    """Length + non-emptiness; saturates around 200 chars."""
    stripped = content.strip()
    if not stripped:
        return 0.0
    n = len(stripped)
    if n < _CLARITY_MIN_LEN:
        return round(n / _CLARITY_MIN_LEN * 0.4, 4)
    return round(min(1.0, n / _CLARITY_TARGET_LEN), 4)


def _evidence_anchoring(refs: list[str]) -> float:
    """More evidence refs => higher anchoring; saturates at 3 refs."""
    n = len(refs)
    if n == 0:
        return 0.0
    return round(min(1.0, n / 3.0), 4)


def _reusability(record: dict[Any, Any]) -> float:
    """Confidence + topic_key + evidence breadth heuristic."""
    confidence = float(record.get("confidence", 0.0))
    has_topic = 1.0 if record.get("topic_key") else 0.0
    # Diversity: more source_refs (provenance breadth) => more reusable
    n_sources = len(record.get("source_refs", []) or [])
    breadth = min(1.0, n_sources / 2.0)
    score = 0.55 * confidence + 0.25 * breadth + 0.2 * has_topic
    if record.get("topic_key"):
        # ponytail: small flat bonus for having a stable topic_key (dedup
        # handle). Bounded so it can't dominate confidence.
        score = min(1.0, score + _REUSABILITY_TOPIC_BONUS)
    return round(min(1.0, max(0.0, score)), 4)


def _temporal_validity(created_at: datetime | None, now: datetime) -> float:
    """Exponential decay from creation; half-life = 60 days."""
    ts = _as_utc(created_at)
    if ts is None:
        return 0.0
    age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
    result: float = round(0.5 ** (age_days / _TEMPORAL_HALF_LIFE_DAYS), 4)
    return result


def score_quality(
    record: Any,
    *,
    now: datetime | None = None,
) -> QualityScoreV2:
    """Compute a four-axis + composite quality score for a v2 record.

    Pure: depends only on the record (and an injected ``now``); deterministic.
    """
    moment = now or datetime.now(tz=UTC)
    rd = _as_dict(record)
    clarity = _clarity(str(rd.get("content", "")))
    evidence = _evidence_anchoring(list(rd.get("evidence_refs", []) or []))
    reuse = _reusability(rd)
    temporal = _temporal_validity(rd.get("created_at"), moment)
    composite = round((clarity + evidence + reuse + temporal) / 4.0, 4)
    return QualityScoreV2(
        clarity=clarity,
        evidence_anchoring=evidence,
        reusability=reuse,
        temporal_validity=temporal,
        composite=composite,
    )


__all__ = ["QualityScoreV2", "score_quality"]

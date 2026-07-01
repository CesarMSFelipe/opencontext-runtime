"""Deterministic conflict detection for Memory v2 (PR-009).

Rules-first: same ``topic_key`` + different content + confidence delta above
threshold = ``CONTRADICTS``. Judgment ids are stable hashes so the same
candidate/existing pair always produces the same envelope.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.compat import StrEnum


class ConflictKindV2(StrEnum):
    """Relation kind for a v2 conflict edge."""

    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    AMBIGUOUS = "ambiguous"


# ponytail: confidence delta default; same threshold as v1 detector so the v2
# rules match the existing store behavior. Tighten only with explicit reason.
DEFAULT_CONFIDENCE_DELTA = 0.3


class ConflictEnvelopeV2(BaseModel):
    """Typed v2 conflict edge between two records."""

    model_config = ConfigDict(extra="forbid")

    record_a: str = Field(description="Id of the incoming candidate.")
    record_b: str = Field(description="Id of the existing record in conflict.")
    kind: ConflictKindV2 = Field(description="Relation kind.")
    reason: str = Field(description="Stable reason code.")
    confidence: float = Field(ge=0.0, le=1.0, description="Detector confidence in [0, 1].")
    judgment_id: str = Field(description="Stable hash id, format rel-<12hex>.")


def _stable_judgment_id(record_a: str, record_b: str) -> str:
    """Stable ``rel-<12hex>`` id derived from the ordered pair."""
    pair = f"{record_a}|{record_b}".encode()
    return f"rel-{hashlib.sha1(pair).hexdigest()[:12]}"


def _as_dict(record: Any) -> dict:
    """Accept either a MemoryRecordV2 instance or a plain dict."""
    if isinstance(record, dict):
        return record
    if hasattr(record, "model_dump"):
        return record.model_dump()
    return {
        "id": getattr(record, "id", ""),
        "topic_key": getattr(record, "topic_key", ""),
        "content": getattr(record, "content", ""),
        "confidence": getattr(record, "confidence", 0.0),
    }


def detect_contradiction(
    candidate: Any,
    existing: list[Any],
    *,
    confidence_delta: float = DEFAULT_CONFIDENCE_DELTA,
) -> list[ConflictEnvelopeV2]:
    """Return typed v2 conflict edges for a candidate against existing records.

    Deterministic: identical inputs always yield the same output, with stable
    ``judgment_id`` per ordered pair. Same-key + same-content is a no-op;
    different-key is a no-op; small confidence delta is treated as a
    refinement, not a contradiction.
    """
    cand = _as_dict(candidate)
    cand_id = cand.get("id", "")
    cand_key = cand.get("topic_key", "")
    cand_content = cand.get("content", "")
    cand_conf = float(cand.get("confidence", 0.0))

    conflicts: list[ConflictEnvelopeV2] = []
    for rec in existing:
        ex = _as_dict(rec)
        ex_id = ex.get("id", "")
        if ex_id == cand_id:
            continue
        if ex.get("topic_key", "") != cand_key:
            continue
        if ex.get("content", "") == cand_content:
            continue
        ex_conf = float(ex.get("confidence", 0.0))
        if abs(ex_conf - cand_conf) <= confidence_delta:
            continue
        # Higher-confidence side wins; kind is CONTRADICTS when the candidate
        # is the new side, SUPERSEDES when the existing is stronger.
        if cand_conf > ex_conf:
            kind = ConflictKindV2.CONTRADICTS
            reason = "same_key_conflicting_content"
        else:
            kind = ConflictKindV2.SUPERSEDES
            reason = "same_key_stronger_existing"
        # Confidence in the detection: 0.5..1.0 scaled by how much the
        # confidence delta exceeds the threshold.
        overshoot = max(0.0, abs(cand_conf - ex_conf) - confidence_delta)
        confidence = round(min(0.5 + overshoot, 1.0), 3)
        conflicts.append(
            ConflictEnvelopeV2(
                record_a=cand_id,
                record_b=ex_id,
                kind=kind,
                reason=reason,
                confidence=confidence,
                judgment_id=_stable_judgment_id(cand_id, ex_id),
            )
        )
    return conflicts


__all__ = [
    "DEFAULT_CONFIDENCE_DELTA",
    "ConflictEnvelopeV2",
    "ConflictKindV2",
    "detect_contradiction",
]

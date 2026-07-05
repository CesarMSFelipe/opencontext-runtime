"""conflict — judgment_required envelope for mem_save.

REQ-OCF-001 — every ``mem_save`` MUST surface a :class:`ConflictEnvelope`
listing the existing observations whose BM25 score clears the configured
floor. The envelope is the machine-readable "is the caller forced to ask the
user" signal: ``judgment_required = True`` iff at least one candidate survives
the floor.

REQ-OCF-004 — judgement heuristic. The surface caller (host agent) MUST ask
the user when confidence is low OR when a "destructive" relation meets a
"high-impact" observation type. Anything else resolves silently.

The envelope is built BEFORE the candidate row is written into
``memory_relations``; ``mem_save`` (``tools/mem_save.py``) calls
:meth:`ConflictEnvelope.materialize` once the new observation id is known so
the pending row can carry ``source_id = new_id`` and ``target_id = candidate.id``.
"""

from __future__ import annotations

from secrets import token_hex
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

BM25_FLOOR_DEFAULT: float = -2.0
"""Default BM25 threshold below which candidates are dropped.

SQLite FTS5 ``bm25()`` returns values where ``0`` is the best match and more
negative values are less relevant. A candidate clears the floor when its
score is strictly greater than ``BM25_FLOOR_DEFAULT`` (i.e. less negative).
"""

_HIGH_IMPACT_TYPES = frozenset({"architecture", "policy", "decision"})
_DESTRUCTIVE_VERBS = frozenset({"supersedes", "conflicts_with"})
_LOW_CONFIDENCE_THRESHOLD = 0.7


class CandidateEnvelope(BaseModel):
    """One BM25-matched candidate in the conflict envelope.

    Carries the minimal record snapshot the caller needs to decide: ``id``
    (to look up later), ``title`` + ``content`` (to show the user), the raw
    ``bm25_score`` (for tuning the floor), and the ``judgment_id`` correlation
    handle that ``mem_judge`` will accept.
    """

    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    content: str
    bm25_score: float
    judgment_id: str = Field(description="Format: rel-<hex> with 8+ hex chars.")
    judgment_status: str = "pending"


class ConflictEnvelope(BaseModel):
    """The full envelope returned alongside every ``SaveReceipt``.

    ``judgment_required`` is a derived flag: it is ``True`` iff at least one
    candidate survived the BM25 floor. ``floor`` and ``query`` are kept on
    the envelope so the caller can re-tune or re-submit without having to
    reconstruct state.
    """

    model_config = ConfigDict(extra="forbid")

    judgment_required: bool
    candidates: list[CandidateEnvelope]
    floor: float
    query: str


def make_judgment_id() -> str:
    """Generate a unique correlation handle.

    Format: ``rel-<hex>`` with at least 8 hex chars (the regex is
    ``^rel-[0-9a-f]{8,}$``; we use 16 hex chars to keep the prefix
    collision-free across 2**64 calls).
    """
    return f"rel-{token_hex(8)}"


def _candidate_from_raw(raw: dict[str, Any]) -> CandidateEnvelope:
    """Coerce one BM25 hit dict into a :class:`CandidateEnvelope`.

    Accepts either an already-built envelope (round-trip via
    :meth:`CandidateEnvelope.model_validate`) or a plain dict shaped like
    the rows :meth:`MemoryStore.search` returns.
    """
    return CandidateEnvelope.model_validate(
        {
            "id": int(raw["id"]),
            "title": str(raw.get("title", "")),
            "content": str(raw.get("content", "")),
            "bm25_score": float(raw["bm25_score"]),
            "judgment_id": make_judgment_id(),
            "judgment_status": "pending",
        }
    )


def build_envelope(
    candidates: list[dict[str, Any]],
    *,
    query: str,
    floor: float = BM25_FLOOR_DEFAULT,
) -> ConflictEnvelope:
    """Filter the BM25 candidates by the floor and wrap them in an envelope.

    BM25 in SQLite FTS5 ranks lower-is-better (more negative = less
    relevant). A candidate clears the floor when its score is strictly
    greater than ``floor`` (i.e. closer to zero). Empty input or empty output
    both yield ``judgment_required = False``; the caller never has to special-
    case the "no candidates at all" branch.
    """
    kept: list[CandidateEnvelope] = []
    for raw in candidates:
        score = float(raw["bm25_score"])
        if score > floor:
            kept.append(_candidate_from_raw(raw))
    return ConflictEnvelope(
        judgment_required=bool(kept),
        candidates=kept,
        floor=float(floor),
        query=str(query),
    )


def should_ask_user(
    *,
    confidence: float,
    relation: str,
    obs_type: str,
) -> bool:
    """Apply the REQ-OCF-004 judgement heuristic.

    ASK the user when:
        ``confidence < 0.7`` OR
        (``relation`` in {supersedes, conflicts_with} AND ``type`` in
        {architecture, policy, decision}).

    Anything else: resolve silently by calling ``mem_judge``.
    """
    if confidence < _LOW_CONFIDENCE_THRESHOLD:
        return True
    if relation in _DESTRUCTIVE_VERBS and obs_type in _HIGH_IMPACT_TYPES:
        return True
    return False


__all__ = [
    "BM25_FLOOR_DEFAULT",
    "CandidateEnvelope",
    "ConflictEnvelope",
    "build_envelope",
    "make_judgment_id",
    "should_ask_user",
]

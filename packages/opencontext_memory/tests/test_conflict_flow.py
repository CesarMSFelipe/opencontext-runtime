"""Tests for the conflict-surfacing envelope flow.

Per strict-TDD: this file is the source of truth for the conflict contract.
``conflict.py`` is written to satisfy these tests.

T2.18 — ``test_REQ_OCF_001_*`` written first (RED). ``conflict.py`` lands
in the same apply batch to turn it GREEN.

REQ-OCF-001 — judgment_required Envelope on Every mem_save
    ``mem_save`` MUST return a ``SaveReceipt`` containing ``receipt``,
    ``judgment_required: bool``, and ``candidates: list[CandidateEnvelope]``.
    Each candidate carries ``judgment_id: str`` formatted as ``rel-<hex>``
    (8+ hex chars).
"""

from __future__ import annotations

import re

import pytest
from opencontext_memory.conflict import (
    BM25_FLOOR_DEFAULT,
    CandidateEnvelope,
    ConflictEnvelope,
    build_envelope,
    make_judgment_id,
    should_ask_user,
)

# ---------------------------------------------------------------------------
# REQ-OCF-001 — envelope build, BM25 floor, judgment_id format (T2.18)
# ---------------------------------------------------------------------------


def test_REQ_OCF_001_bm25_floor_default_is_minus_two() -> None:
    """The default floor MUST be -2.0 (per design.md §Memory Conflict Flow).

    Pinning it in a test prevents a silent refactor from drifting the
    threshold and suddenly returning 10 candidates per save.
    """
    assert BM25_FLOOR_DEFAULT == -2.0


def test_REQ_OCF_001_make_judgment_id_matches_correlation_handle_pattern() -> None:
    """``judgment_id`` is the correlation handle between ``mem_save`` and
    ``mem_judge``. Format: ``rel-<hex>`` with 8+ hex chars.
    """
    for _ in range(50):
        jid = make_judgment_id()
        assert re.match(r"^rel-[0-9a-f]{8,}$", jid), (
            f"judgment_id {jid!r} does not match ^rel-[0-9a-f]{(8,)}$"
        )


def test_REQ_OCF_001_make_judgment_id_is_unique_under_repeated_calls() -> None:
    """Triangulation: the generator is collision-resistant enough that 1 000
    sequential calls produce no duplicates. (UUID4 has 122 effective bits.)
    """
    seen = {make_judgment_id() for _ in range(1000)}
    assert len(seen) == 1000


def test_REQ_OCF_001_build_envelope_empty_candidates_yields_judgment_required_false() -> None:
    """When no BM25 hit clears the floor, the envelope is empty AND
    ``judgment_required`` is ``False``. ``mem_save`` proceeds normally.
    """
    envelope = build_envelope([], query="login", floor=-2.0)
    assert isinstance(envelope, ConflictEnvelope)
    assert envelope.judgment_required is False
    assert envelope.candidates == []
    assert envelope.query == "login"
    assert envelope.floor == -2.0


def test_REQ_OCF_001_build_envelope_filters_candidates_below_bm25_floor() -> None:
    """A candidate with a BM25 score WORSE than the floor (more negative than
    -2.0) MUST be dropped. A candidate with a score CLOSER to zero than the
    floor (e.g. -1.0) MUST be kept. ``judgment_required`` follows the kept set.
    """
    raw = [
        {"id": 1, "title": "Strong match", "content": "...", "bm25_score": -0.5},
        {"id": 2, "title": "Barely relevant", "content": "...", "bm25_score": -1.9},
        {"id": 3, "title": "Below floor", "content": "...", "bm25_score": -2.5},
        {"id": 4, "title": "Far below floor", "content": "...", "bm25_score": -7.0},
    ]
    envelope = build_envelope(raw, query="login", floor=-2.0)
    assert envelope.judgment_required is True
    assert [c.id for c in envelope.candidates] == [1, 2]


def test_REQ_OCF_001_build_envelope_attaches_correlation_handle_per_candidate() -> None:
    """Each kept candidate gets a unique ``judgment_id`` matching the
    correlation-handle pattern.
    """
    raw = [
        {"id": 10, "title": "A", "content": "A", "bm25_score": -0.4},
        {"id": 20, "title": "B", "content": "B", "bm25_score": -0.9},
    ]
    envelope = build_envelope(raw, query="auth", floor=-2.0)
    ids = [c.judgment_id for c in envelope.candidates]
    assert len(ids) == 2
    for jid in ids:
        assert re.match(r"^rel-[0-9a-f]{8,}$", jid)
    assert len(set(ids)) == 2, "each candidate needs a unique judgment_id"


def test_REQ_OCF_001_build_envelope_honours_custom_floor() -> None:
    """The caller can tighten the floor; the tighter threshold trims more.
    Triangulation: same input, different floors, different kept sets.
    """
    raw = [{"id": 1, "title": "x", "content": "x", "bm25_score": -1.5}]

    loose = build_envelope(raw, query="x", floor=-2.0)
    tight = build_envelope(raw, query="x", floor=-1.0)

    assert loose.judgment_required is True
    assert tight.judgment_required is False


def test_REQ_OCF_001_build_envelope_preserves_candidate_metadata() -> None:
    """The :class:`CandidateEnvelope` carries ``id``, ``title``, ``content``,
    ``bm25_score``, ``judgment_id``, and ``judgment_status='pending'``."""
    raw = [{"id": 42, "title": "Login bug", "content": "500 on POST", "bm25_score": -0.3}]
    envelope = build_envelope(raw, query="login", floor=-2.0)

    assert len(envelope.candidates) == 1
    cand = envelope.candidates[0]
    assert isinstance(cand, CandidateEnvelope)
    assert cand.id == 42
    assert cand.title == "Login bug"
    assert cand.content == "500 on POST"
    assert cand.bm25_score == pytest.approx(-0.3)
    assert cand.judgment_status == "pending"
    assert re.match(r"^rel-[0-9a-f]{8,}$", cand.judgment_id)


# ---------------------------------------------------------------------------
# REQ-OCF-004 — judgement heuristic for the surface caller
# ---------------------------------------------------------------------------


def test_REQ_OCF_004_should_ask_user_on_low_confidence() -> None:
    """confidence < 0.7 → ASK."""
    assert should_ask_user(confidence=0.6, relation="related", obs_type="decision") is True


def test_REQ_OCF_004_should_ask_user_on_supersedes_architecture() -> None:
    """supersedes/conflicts_with AND architecture/policy/decision → ASK
    (even at high confidence)."""
    assert should_ask_user(confidence=0.9, relation="supersedes", obs_type="architecture") is True
    assert should_ask_user(confidence=0.95, relation="conflicts_with", obs_type="policy") is True


def test_REQ_OCF_004_should_resolve_silently_on_safe_pair() -> None:
    """High confidence + safe relation + safe type → resolve silently."""
    assert should_ask_user(confidence=0.9, relation="related", obs_type="decision") is False
    assert should_ask_user(confidence=0.8, relation="compatible", obs_type="bugfix") is False

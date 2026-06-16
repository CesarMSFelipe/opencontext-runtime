"""Tests for compute_hybrid_score — pure function, no mocks."""

from opencontext_core.retrieval.scoring import RetrievalWeights, compute_hybrid_score

_BASE = dict(
    candidate_id="item1",
    candidate_source="src/foo.py",
    candidate_source_type="file",
    candidate_source_trust=0.8,
    candidate_modified_at=None,
    candidate_tokens=100,
    lexical_score=0.5,
    memory_boost_map={},
    graph_distance_map={},
    is_required=False,
    is_test=False,
)


def test_required_scores_higher_than_not_required():
    score_req = compute_hybrid_score(**{**_BASE, "is_required": True})
    score_not = compute_hybrid_score(**{**_BASE, "is_required": False})
    assert score_req > score_not


def test_memory_boost_increases_score():
    score_boosted = compute_hybrid_score(**{**_BASE, "memory_boost_map": {"item1": 0.9}})
    score_plain = compute_hybrid_score(**_BASE)
    assert score_boosted > score_plain


def test_test_affinity_increases_score():
    score_test = compute_hybrid_score(**{**_BASE, "is_test": True})
    score_no_test = compute_hybrid_score(**{**_BASE, "is_test": False})
    assert score_test > score_no_test


def test_graph_distance_zero_higher_than_five():
    score_close = compute_hybrid_score(**{**_BASE, "graph_distance_map": {"item1": 0}})
    score_far = compute_hybrid_score(**{**_BASE, "graph_distance_map": {"item1": 5}})
    assert score_close > score_far


def test_stale_reduces_score():
    score_fresh = compute_hybrid_score(**{**_BASE, "is_stale": False})
    score_stale = compute_hybrid_score(**{**_BASE, "is_stale": True})
    assert score_stale < score_fresh


def test_uncertain_reduces_score():
    score_certain = compute_hybrid_score(**{**_BASE, "is_uncertain": False})
    score_uncertain = compute_hybrid_score(**{**_BASE, "is_uncertain": True})
    assert score_uncertain < score_certain


def test_score_never_negative():
    # Maximize penalties
    score = compute_hybrid_score(
        candidate_id="item1",
        candidate_source="src",
        candidate_source_type="file",
        candidate_source_trust=0.0,
        candidate_modified_at=None,
        candidate_tokens=100_000,
        lexical_score=0.0,
        memory_boost_map={},
        graph_distance_map={"item1": 999},
        is_required=False,
        is_test=False,
        memory_confidence=0.0,
        is_stale=True,
        is_uncertain=True,
    )
    assert score >= 0.0


def test_default_weights_positive_sum_less_than_one():
    w = RetrievalWeights()
    positive_sum = (
        w.semantic_relevance
        + w.graph_centrality
        + w.call_distance
        + w.test_affinity
        + w.memory_confidence
        + w.recent_failure
        + w.risk_requirement
        + w.freshness
        + w.provenance
    )
    # Positive weights should sum to <= 1.0 (they sum to exactly 1.0)
    assert positive_sum <= 1.0

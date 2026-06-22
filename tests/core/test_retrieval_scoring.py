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


def test_definition_of_queried_symbol_outranks_its_test():
    # "add/modify <Symbol>" must surface the file where <Symbol> is DEFINED, not its
    # test. The defining symbol (is_definition=True) carries a query-name match; the
    # test merely has the same lexical relevance. The definition must win.
    defining = compute_hybrid_score(**{**_BASE, "is_definition": True, "is_test": False})
    test_file = compute_hybrid_score(**{**_BASE, "is_definition": False, "is_test": True})
    assert defining > test_file


def test_definition_boost_increases_score():
    score_def = compute_hybrid_score(**{**_BASE, "is_definition": True})
    score_plain = compute_hybrid_score(**{**_BASE, "is_definition": False})
    assert score_def > score_plain


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
        + w.definition
        + w.freshness
        + w.provenance
    )
    # The ten core positive weights should sum to <= 1.0 (they sum to exactly 1.0 in
    # exact arithmetic; allow float epsilon). ``personalization`` is a 0.01 tie-breaker.
    assert positive_sum <= 1.0 + 1e-9

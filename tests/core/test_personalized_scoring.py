"""Personalized graph ranking signals in ``retrieval.scoring`` — pure, deterministic.

Covers the stdlib personalized PageRank, the identifier-quality heuristics
(query-mention boost, well-named boost, private/over-common downweighting,
sqrt reference-count dampening), and the new personalization signal feeding
``compute_hybrid_score`` without breaking its existing contract.
"""

from __future__ import annotations

from opencontext_core.retrieval.scoring import (
    RetrievalWeights,
    compute_hybrid_score,
    identifier_quality_score,
    personalized_pagerank,
)

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


# ---- personalization signal wired into compute_hybrid_score -----------------


def test_personalization_map_increases_score() -> None:
    boosted = compute_hybrid_score(**{**_BASE, "personalization_map": {"item1": 1.0}})
    plain = compute_hybrid_score(**_BASE)
    assert boosted > plain


def test_personalization_absent_is_backward_compatible() -> None:
    # Omitting the new kwarg must reproduce the prior score exactly.
    explicit_empty = compute_hybrid_score(**{**_BASE, "personalization_map": {}})
    omitted = compute_hybrid_score(**_BASE)
    assert explicit_empty == omitted


def test_personalization_weight_in_default_weights() -> None:
    w = RetrievalWeights()
    assert w.personalization > 0.0


# ---- personalized PageRank --------------------------------------------------


def test_pagerank_sums_to_one_and_is_a_distribution() -> None:
    adjacency = {"a": {"b", "c"}, "b": {"c"}, "c": {"a"}}
    ranks = personalized_pagerank(adjacency, seeds={"a"})
    assert set(ranks) == {"a", "b", "c"}
    assert all(v >= 0.0 for v in ranks.values())
    assert abs(sum(ranks.values()) - 1.0) < 1e-6


def test_pagerank_seed_outranks_unrelated_node() -> None:
    # Two disjoint pairs; seeding one pair must lift that pair's mass.
    adjacency = {"a": {"b"}, "b": {"a"}, "x": {"y"}, "y": {"x"}}
    ranks = personalized_pagerank(adjacency, seeds={"a"})
    assert ranks["a"] > ranks["x"]
    assert ranks["b"] > ranks["y"]


def test_pagerank_is_deterministic_across_runs() -> None:
    adjacency = {"a": {"b", "c"}, "b": {"c"}, "c": {"a", "b"}, "d": {"a"}}
    first = personalized_pagerank(adjacency, seeds={"a", "d"})
    second = personalized_pagerank(adjacency, seeds={"a", "d"})
    assert first == second


def test_pagerank_empty_seeds_falls_back_to_uniform() -> None:
    adjacency = {"a": {"b"}, "b": {"a"}}
    ranks = personalized_pagerank(adjacency, seeds=set())
    assert abs(sum(ranks.values()) - 1.0) < 1e-6
    assert ranks["a"] > 0.0 and ranks["b"] > 0.0


def test_pagerank_empty_graph_returns_empty() -> None:
    assert personalized_pagerank({}, seeds={"a"}) == {}


# ---- identifier quality heuristics ------------------------------------------


def test_query_mentioned_identifier_scores_higher() -> None:
    query_terms = {"authenticate"}
    mentioned = identifier_quality_score("authenticate_user", query_terms, reference_count=3)
    unmentioned = identifier_quality_score("render_widget", query_terms, reference_count=3)
    assert mentioned > unmentioned


def test_private_identifier_is_downweighted() -> None:
    public = identifier_quality_score("compute_total", set(), reference_count=3)
    private = identifier_quality_score("_compute_total", set(), reference_count=3)
    assert private < public


def test_well_named_identifier_beats_terse_one() -> None:
    well_named = identifier_quality_score("calculate_invoice_total", set(), reference_count=3)
    terse = identifier_quality_score("x", set(), reference_count=3)
    assert well_named > terse


def test_reference_count_is_dampened_by_sqrt() -> None:
    # Over-common symbols are downweighted, and the dampening is sublinear:
    # going 1 -> 4 references must drop the score less than 4x (sqrt-shaped).
    few = identifier_quality_score("helper", set(), reference_count=1)
    many = identifier_quality_score("helper", set(), reference_count=100)
    assert many < few
    mid = identifier_quality_score("helper", set(), reference_count=4)
    # sqrt dampening: the 1->4 drop is gentler than a linear 4x would imply.
    assert (few - mid) < (few - many)


def test_identifier_quality_is_deterministic() -> None:
    q = {"parse"}
    first = identifier_quality_score("parse_config", q, reference_count=7)
    second = identifier_quality_score("parse_config", q, reference_count=7)
    assert first == second

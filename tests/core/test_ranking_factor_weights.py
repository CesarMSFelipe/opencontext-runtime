"""CTX-RANKING-FACTORS tests: DOC2 §13.3 ranking factors — directional behavior
for the two previously untested families (recency/freshness and size penalty)
plus the reconciliation pin between the documented initial weights and the
shipped ``RetrievalWeights`` defaults.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from opencontext_core.compat import UTC
from opencontext_core.retrieval.scoring import RetrievalWeights, compute_hybrid_score


def _score(*, modified_at: str | None = None, tokens: int = 100) -> float:
    return compute_hybrid_score(
        candidate_id="cand",
        candidate_source="src/mod.py",
        candidate_source_type="file",
        candidate_source_trust=0.8,
        candidate_modified_at=modified_at,
        candidate_tokens=tokens,
        lexical_score=0.7,
        memory_boost_map={},
        graph_distance_map={},
        is_required=False,
        is_test=False,
    )


def test_freshness_newer_candidate_scores_higher() -> None:
    """CTX-RANKING-FACTORS: recency (DOC2 §13.3 'Recencia/cambios recientes') —
    an otherwise identical candidate modified yesterday outscores one modified
    a year ago (directional freshness boost)."""
    now = datetime.now(tz=UTC)
    fresh = _score(modified_at=(now - timedelta(days=1)).isoformat())
    stale = _score(modified_at=(now - timedelta(days=365)).isoformat())
    assert fresh > stale


def test_token_cost_penalty_bigger_candidate_scores_lower() -> None:
    """CTX-RANKING-FACTORS: size penalty (DOC2 §13.3 'Penalización por tamaño')
    — an otherwise identical candidate with a much larger token cost scores
    lower (directional token-cost penalty)."""
    small = _score(tokens=50)
    big = _score(tokens=9_000)
    assert small > big


def test_shipped_default_weights_reconciled_with_documented_initial_weights() -> None:
    """CTX-RANKING-FACTORS: reconciliation pin — DOC2 §13.3 and
    KG_CONTEXT_COMPRESSION_CONTRACT document RECOMMENDED initial weights
    (direct match 0.30, KG neighborhood 0.25, related tests 0.15, recency 0.10,
    memory 0.10, centrality 0.05, size penalty -0.05). The shipped
    ``RetrievalWeights`` defaults are deliberately different (tuned; RD1 single
    source of truth) and are pinned here; ``context.ranking`` config overrides
    (tests/core/test_ranking_config_overrides.py) let a project opt into the
    documented numbers. All seven documented factor families map onto shipped
    fields:

    - direct task match  -> semantic_relevance (+ definition affinity)
    - KG neighborhood    -> call_distance (+ graph expansion distance)
    - related tests      -> test_affinity
    - recency            -> freshness (+ recent_failure)
    - linked memory      -> memory_confidence
    - centrality/impact  -> graph_centrality
    - size penalty       -> token_cost_penalty
    """
    weights = RetrievalWeights()

    # Shipped defaults, pinned so any drift is a conscious contract decision.
    assert weights.semantic_relevance == 0.34
    assert weights.graph_centrality == 0.13
    assert weights.call_distance == 0.08
    assert weights.test_affinity == 0.05
    assert weights.memory_confidence == 0.07
    assert weights.recent_failure == 0.06
    assert weights.risk_requirement == 0.05
    assert weights.definition == 0.18
    assert weights.freshness == 0.02
    assert weights.provenance == 0.02
    assert weights.token_cost_penalty == 0.03

    # Every documented factor family exists as a positive (or penalty) knob.
    for field in (
        "semantic_relevance",
        "call_distance",
        "test_affinity",
        "freshness",
        "memory_confidence",
        "graph_centrality",
        "token_cost_penalty",
    ):
        assert hasattr(weights, field), f"documented factor family missing: {field}"

    # The ten core positive weights keep their sum-to-1.0 invariant.
    core_sum = (
        weights.semantic_relevance
        + weights.graph_centrality
        + weights.call_distance
        + weights.test_affinity
        + weights.memory_confidence
        + weights.recent_failure
        + weights.risk_requirement
        + weights.definition
        + weights.freshness
        + weights.provenance
    )
    assert abs(core_sum - 1.0) < 1e-9


def test_documented_factor_families_are_config_overridable() -> None:
    """CTX-RANKING-FACTORS: every documented factor family that maps onto a
    ``RetrievalWeights`` positive weight is overridable via ``context.ranking``
    (the escape hatch to opt into the DOC2 §13.3 initial weights)."""
    from opencontext_core.retrieval.planner import _RANKING_OVERRIDE_FIELDS

    for field in (
        "semantic_relevance",
        "graph_centrality",
        "call_distance",
        "test_affinity",
        "memory_confidence",
        "freshness",
    ):
        assert field in _RANKING_OVERRIDE_FIELDS, f"{field} must be config-overridable"

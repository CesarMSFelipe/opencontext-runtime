"""Hybrid retrieval scoring — pure functions, no side effects.

In addition to :func:`compute_hybrid_score`, this module provides the building
blocks for personalized graph ranking: a stdlib personalized PageRank
(:func:`personalized_pagerank`) and the identifier-quality heuristics
(:func:`identifier_quality_score`) used to seed and weight it. Everything here is
pure and deterministic so identical inputs always produce identical scores.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RetrievalWeights:
    semantic_relevance: float = 0.40
    graph_centrality: float = 0.16
    call_distance: float = 0.10
    test_affinity: float = 0.05
    memory_confidence: float = 0.08
    recent_failure: float = 0.07
    risk_requirement: float = 0.06
    personalization: float = 0.01
    freshness: float = 0.04
    provenance: float = 0.03
    # Penalties
    stale_memory_penalty: float = 0.05
    token_cost_penalty: float = 0.03
    uncertainty_penalty: float = 0.02


def compute_hybrid_score(
    candidate_id: str,
    candidate_source: str,
    candidate_source_type: str,
    candidate_source_trust: float,
    candidate_modified_at: str | None,
    candidate_tokens: int,
    lexical_score: float,
    memory_boost_map: dict[str, float],
    graph_distance_map: dict[str, int],
    is_required: bool,
    is_test: bool,
    weights: RetrievalWeights | None = None,
    memory_confidence: float = 1.0,
    is_stale: bool = False,
    is_uncertain: bool = False,
    personalization_map: dict[str, float] | None = None,
) -> float:
    """Pure function. No side effects. Deterministic.

    ``personalization_map`` is an optional per-candidate signal (typically a
    query-seeded personalized PageRank over the candidate call graph). Omitting
    it leaves the score identical to the prior contract.
    """
    w = weights or RetrievalWeights()

    sem_rel = max(0.0, min(1.0, lexical_score))
    centrality = _normalize_distance(graph_distance_map.get(candidate_id, 999))
    call_dist = centrality
    # Test affinity rides on the candidate's OWN lexical relevance rather than
    # being a flat per-test bonus. A flat bonus made every test file outrank
    # equally/more relevant non-test source (the bonus, 0.10, dwarfed the lexical
    # contribution), so "where is X defined" returned X's tests, not X. Gating by
    # sem_rel keeps genuinely-relevant tests as useful context without that bias.
    test_aff = sem_rel if is_test else 0.0
    mem_conf = max(0.0, min(1.0, memory_confidence))
    fail_boost = max(0.0, min(1.0, memory_boost_map.get(candidate_id, 0.0)))
    risk_req = 1.0 if is_required else 0.0
    personal = 0.0
    if personalization_map:
        personal = max(0.0, min(1.0, personalization_map.get(candidate_id, 0.0)))
    fresh = _compute_freshness(candidate_modified_at)
    prov = max(0.0, min(1.0, candidate_source_trust))

    positive = (
        sem_rel * w.semantic_relevance
        + centrality * w.graph_centrality
        + call_dist * w.call_distance
        + test_aff * w.test_affinity
        + mem_conf * w.memory_confidence
        + fail_boost * w.recent_failure
        + risk_req * w.risk_requirement
        + personal * w.personalization
        + fresh * w.freshness
        + prov * w.provenance
    )
    penalty = (
        (w.stale_memory_penalty if is_stale else 0.0)
        + w.token_cost_penalty * min(1.0, candidate_tokens / 10_000)
        + (w.uncertainty_penalty if is_uncertain else 0.0)
    )
    return max(0.0, positive - penalty)


def _normalize_distance(distance: int) -> float:
    """0→1.0, 1→0.8, 2→0.6, 3→0.4, 4→0.2, 5+→0.0"""
    return max(0.0, 1.0 - distance * 0.2)


def _compute_freshness(modified_at: str | None) -> float:
    if not modified_at:
        return 0.7
    try:
        dt = datetime.fromisoformat(modified_at)
        now = datetime.now(tz=dt.tzinfo) if dt.tzinfo is not None else datetime.now()
        days = (now - dt).days
        return max(0.5, 1.0 - days * 0.01)
    except (ValueError, TypeError):
        return 0.7


# ---- personalized graph ranking primitives ----------------------------------

_PRIVATE_PENALTY = 0.5
_OVER_COMMON_THRESHOLD = 32


def personalized_pagerank(
    adjacency: Mapping[str, Set[str]],
    seeds: Set[str],
    *,
    damping: float = 0.85,
    max_iterations: int = 100,
    tolerance: float = 1.0e-9,
) -> dict[str, float]:
    """Deterministic personalized PageRank over a directed adjacency map.

    ``adjacency`` maps each node id to the set of node ids it points to. The
    teleport (restart) distribution is concentrated on ``seeds``; when ``seeds``
    is empty it falls back to a uniform restart (i.e. classic PageRank). The
    returned ranks form a probability distribution (sum ~= 1.0) and are
    reproducible for identical inputs because every iteration walks nodes in
    sorted order. Dangling nodes (no out-edges) redistribute their mass to the
    teleport distribution so probability mass is conserved.
    """

    nodes = sorted(adjacency)
    n = len(nodes)
    if n == 0:
        return {}

    node_set = set(nodes)
    out_links: dict[str, list[str]] = {
        node: sorted(t for t in adjacency.get(node, ()) if t in node_set) for node in nodes
    }

    valid_seeds = sorted(s for s in seeds if s in node_set)
    if valid_seeds:
        teleport_mass = 1.0 / len(valid_seeds)
        teleport = {node: (teleport_mass if node in set(valid_seeds) else 0.0) for node in nodes}
    else:
        uniform = 1.0 / n
        teleport = {node: uniform for node in nodes}

    rank = {node: teleport[node] for node in nodes}
    for _ in range(max_iterations):
        dangling_mass = sum(rank[node] for node in nodes if not out_links[node])
        next_rank = {
            node: (1.0 - damping) * teleport[node] + damping * dangling_mass * teleport[node]
            for node in nodes
        }
        for node in nodes:
            targets = out_links[node]
            if not targets:
                continue
            share = damping * rank[node] / len(targets)
            for target in targets:
                next_rank[target] += share
        delta = sum(abs(next_rank[node] - rank[node]) for node in nodes)
        rank = next_rank
        if delta < tolerance:
            break

    total = sum(rank.values())
    if total > 0.0:
        rank = {node: value / total for node, value in rank.items()}
    return rank


def identifier_quality_score(
    name: str,
    query_terms: Iterable[str],
    *,
    reference_count: int = 0,
) -> float:
    """Heuristic [0, 1] quality/relevance score for a symbol identifier.

    Boosts identifiers whose tokens appear in the query, rewards well-formed
    multi-token names, downweights private (leading-underscore) identifiers and
    over-common ones, and dampens the reference count by its square root so a
    heavily-referenced symbol is downweighted sublinearly rather than dominating.
    Pure and deterministic.
    """

    tokens = _split_identifier(name)
    query_set = {term.lower() for term in query_terms if term}

    base = 0.35
    if tokens:
        overlap = sum(1 for token in tokens if token in query_set)
        if overlap:
            base += 0.4 * min(1.0, overlap / len(tokens))

    # Well-named: multi-token, readable identifiers (not 1-2 char throwaways).
    stripped = name.lstrip("_")
    if len(tokens) >= 2:
        base += 0.15
    if len(stripped) >= 3:
        base += 0.1

    score = max(0.0, min(1.0, base))

    if name.startswith("_"):
        score *= _PRIVATE_PENALTY

    # Sqrt dampening: sublinear decay with reference count, with an extra
    # downweight once a symbol is so common it is unlikely to be discriminating.
    damp = 1.0 / (1.0 + math.sqrt(max(0, reference_count)))
    score *= damp
    if reference_count > _OVER_COMMON_THRESHOLD:
        score *= 0.75

    return max(0.0, min(1.0, score))


def _split_identifier(name: str) -> list[str]:
    """Split a snake_case / camelCase identifier into lowercase word tokens."""

    tokens: list[str] = []
    for chunk in name.replace("-", "_").split("_"):
        if not chunk:
            continue
        word = ""
        prev_lower = False
        for ch in chunk:
            if ch.isupper() and prev_lower:
                if word:
                    tokens.append(word.lower())
                word = ch
            else:
                word += ch
            prev_lower = ch.islower()
        if word:
            tokens.append(word.lower())
    return tokens

"""Deterministic context ranking.

Two-way unification (problem 1): ``ContextRanker`` historically used a 4-weight
formula (``relevance`` + ``priority`` + ``source_trust`` + ``token_efficiency``)
returning a score in [0, 1]. The rest of the runtime uses
``RetievalWeights`` + ``compute_hybrid_score`` (14 weights). A user setting
``context.ranking.recent_failure: 0.20`` only affected the latter path, so the
legacy formula could ignore half the config's intent. This module now delegates
the per-item score to ``compute_hybrid_score`` with weights derived from the
config's ranking weights, making both paths score items identically while
preserving the public ``.rank(items) -> items`` API.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from opencontext_core.compat import UTC
from opencontext_core.config import RankingWeightsConfig
from opencontext_core.models.context import ContextItem
from opencontext_core.retrieval.scoring import (
    RetrievalWeights,
    compute_hybrid_score,
)

SOURCE_TRUST: dict[str, float] = {
    "system": 1.0,
    "project_manifest": 0.9,
    "symbol": 0.85,
    "file": 0.8,
    "memory": 0.75,
    "conversation": 0.65,
    "tool": 0.6,
}


class ContextRanker:
    """Ranks context items with the SAME formula the planner / scoring use.

    Back-compat surface: ``.rank(items) -> items`` sorted by score desc. The
    scoring formula is now :func:`opencontext_core.retrieval.scoring.compute_hybrid_score`
    with weights derived from :class:`RankingWeightsConfig`, so WorkflowEngine
    and the planner / verify path agree on rankings for the same input.
    """

    def __init__(self, weights: RankingWeightsConfig) -> None:
        self.weights = weights
        self._retrieval_weights = _retrieval_weights_from_config(weights)

    def rank(self, items: list[ContextItem]) -> list[ContextItem]:
        """Return ranked copies of context items in descending score order."""

        ranked = [self._score_item(item) for item in items]
        return sorted(
            ranked,
            key=lambda item: (-item.score, int(item.priority), item.tokens, item.id),
        )

    def _score_item(self, item: ContextItem) -> ContextItem:
        retrieval_relevance = max(0.0, min(1.0, item.score))
        source_trust = SOURCE_TRUST.get(item.source_type, 0.5)
        modified_at_raw = item.metadata.get("modified_at")
        modified_at = modified_at_raw if isinstance(modified_at_raw, str) else None
        # ``compute_hybrid_score`` is the single source of truth; same call site
        # used by :class:`RetrievalPlanner.rank`. ``memory_boost_map`` and
        # ``graph_distance_map`` are empty here because legacy
        # ``ContextRanker.rank`` callers do not supply them; the missing
        # signals simply contribute 0 (preserving the previous Conservation
        # property).
        score = compute_hybrid_score(
            candidate_id=item.id,
            candidate_source=item.source,
            candidate_source_type=item.source_type,
            candidate_source_trust=source_trust,
            candidate_modified_at=modified_at,
            candidate_tokens=item.tokens,
            lexical_score=retrieval_relevance,
            memory_boost_map={},
            graph_distance_map={},
            is_required=item.priority.value <= 1,  # P0/P1 → required
            is_test=False,
            weights=self._retrieval_weights,
            memory_confidence=self.weights.priority,
        )
        metadata = dict(item.metadata)
        metadata["ranking"] = {
            "retrieval_relevance": retrieval_relevance,
            "priority_score": (5 - int(item.priority)) / 5,
            "source_trust": source_trust,
            "token_efficiency": 1 / (1 + (item.tokens / 1000)),
            "recency_bonus": _recency_bonus(item),
            "formula": (
                "compute_hybrid_score via RetrievalWeights derived from "
                "RankingWeightsConfig (single source of truth — see "
                "opencontext_core.retrieval.scoring)"
            ),
        }
        return item.model_copy(update={"score": round(score, 6), "metadata": metadata})


def _retrieval_weights_from_config(cfg: RankingWeightsConfig) -> RetrievalWeights:
    """Derive a 14-field ``RetrievalWeights`` from the legacy 4-field config.

    Only the four legacy fields are mapped; ``RetrievalWeights`` keeps its
    document defaults for the rest. The user can opt into the other signals
    (``graph_centrality``, ``recent_failure``, ``definition``, ``freshness``
    etc.) by switching to ``context.ranking`` v2 fields in their
    ``opencontext.yaml``, which the planner already honors.
    ``priority`` maps to ``memory_confidence`` so a high priority weight boosts
    candidates carrying the user's required-symbol flag.
    """
    return dataclasses.replace(
        RetrievalWeights(),
        semantic_relevance=cfg.relevance,
        memory_confidence=cfg.priority,
        provenance=cfg.source_trust,
        # token_efficiency is a negative signal in hybrid; map via
        # token_cost_penalty so a higher config weight → stronger penalisation.
        token_cost_penalty=cfg.token_efficiency,
    )


def _recency_bonus(item: ContextItem) -> float:
    raw_modified_at = item.metadata.get("modified_at")
    if not isinstance(raw_modified_at, str):
        return 0.0
    try:
        modified_at = datetime.fromisoformat(raw_modified_at)
    except ValueError:
        return 0.0
    if modified_at.tzinfo is None:
        modified_at = modified_at.replace(tzinfo=UTC)
    age_days = max(0, (datetime.now(tz=UTC) - modified_at.astimezone(UTC)).days)
    if age_days <= 7:
        return 0.05
    if age_days <= 30:
        return 0.03
    if age_days <= 180:
        return 0.01
    return 0.0

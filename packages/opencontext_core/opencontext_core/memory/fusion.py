"""Reciprocal-rank fusion for combining ranked result lists.

RRF merges several independently-ranked lists into one without needing
calibrated scores: each item earns ``1 / (k + rank)`` from every list it
appears in, and items are ordered by the summed contribution. ``k`` dampens
the influence of the very top ranks so that broad agreement across lists wins
over a single list's top hit.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence

DEFAULT_K = 60


def reciprocal_rank_fusion[T: Hashable](
    ranked_lists: Sequence[Sequence[T]], *, k: int = DEFAULT_K
) -> list[T]:
    """Fuse ranked lists into a single ranking, most relevant first.

    Ties (equal fused score) keep the order of first appearance, so a single
    list is returned unchanged.
    """
    scores: dict[T, float] = {}
    first_seen: dict[T, int] = {}
    order = 0
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank + 1)
            if item not in first_seen:
                first_seen[item] = order
                order += 1
    return sorted(scores, key=lambda item: (-scores[item], first_seen[item]))

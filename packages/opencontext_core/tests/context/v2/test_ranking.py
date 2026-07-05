"""Tests for context.v2.ranking — BM25 + recency ranker (CONV2 #9)."""

from __future__ import annotations

from opencontext_core.context.v2.ranking import ContextRanker


def test_rank_orders_by_bm25_score_desc() -> None:
    ranker = ContextRanker()
    items = [
        {"id": "a", "content": "auth login flow"},
        {"id": "b", "content": "unrelated docs about weather"},
        {"id": "c", "content": "auth token validation"},
    ]
    ranked = ranker.rank(items, "auth")
    ids = [item["id"] for item in ranked]
    # items a and c match "auth" -> should come before b
    assert ids[0] in {"a", "c"}
    assert ids[-1] == "b"


def test_rank_empty_query_returns_input_order() -> None:
    ranker = ContextRanker()
    items = [{"id": "x", "content": "anything"}]
    ranked = ranker.rank(items, "")
    assert ranked == items


def test_rank_uses_recency_signal() -> None:
    # recency closer to 1.0 should beat older content with same BM25 overlap
    ranker = ContextRanker()
    items = [
        {"id": "old", "content": "auth bug fix", "recency": 0.1},
        {"id": "new", "content": "auth bug fix", "recency": 0.9},
    ]
    ranked = ranker.rank(items, "auth bug")
    assert ranked[0]["id"] == "new"

"""Diversity-aware (MMR) selection: covers distinct facets, not near-duplicates."""

from __future__ import annotations

from opencontext_core.models.context import ContextItem, ContextPriority
from opencontext_core.retrieval.planner import select_diverse


def _item(item_id: str, content: str, score: float) -> ContextItem:
    return ContextItem(
        id=item_id,
        source=f"{item_id}.py",
        source_type="file",
        content=content,
        priority=ContextPriority.P1,
        tokens=10,
        score=score,
    )


def test_keeps_all_when_k_at_least_count():
    items = [_item("a", "x", 1.0), _item("b", "y", 0.9)]
    assert select_diverse(items, 5) == items  # nothing to trade off
    assert select_diverse(items, 2) == items


def test_demotes_near_duplicate_in_favor_of_distinct_facet():
    # A and B are near-identical; C covers a different facet.
    a = _item("a", "auth login token validation flow", 1.0)
    b = _item("b", "auth login token validation flow now", 0.95)  # near-dup of A
    c = _item("c", "billing invoice payment retry schedule", 0.90)  # distinct
    picked = select_diverse([a, b, c], 2)
    ids = [it.id for it in picked]
    assert ids[0] == "a"  # the most relevant item always leads
    assert "c" in ids  # the distinct facet beats the near-duplicate
    assert "b" not in ids


def test_pure_relevance_order_when_all_distinct():
    a = _item("a", "alpha alpha", 1.0)
    b = _item("b", "bravo bravo", 0.9)
    c = _item("c", "charlie charlie", 0.8)
    # No redundancy to penalize -> relevance order is preserved.
    assert [it.id for it in select_diverse([a, b, c], 3)] == ["a", "b", "c"]


def test_deterministic():
    items = [_item(str(i), f"content variant {i % 3}", 1.0 - i * 0.01) for i in range(8)]
    first = [it.id for it in select_diverse(items, 4)]
    second = [it.id for it in select_diverse(items, 4)]
    assert first == second


def test_empty_and_zero_k():
    assert select_diverse([], 5) == []
    assert select_diverse([_item("a", "x", 1.0)], 0) == []

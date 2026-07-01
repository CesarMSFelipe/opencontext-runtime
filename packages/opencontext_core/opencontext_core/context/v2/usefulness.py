from __future__ import annotations

from typing import Any

"""Context v2 usefulness — CONV2 #11 content-to-query relevance."""


def usefulness_score(item: dict[Any, Any], query: str) -> float:
    """Fraction of query terms found in item content."""
    if not query:
        return 0.0
    content = item.get("content", "")
    if not content:
        return 0.0
    q_terms = set(query.lower().split())
    c_terms = set(content.lower().split())
    if not q_terms:
        return 0.0
    return len(q_terms & c_terms) / len(q_terms)


__all__ = ["usefulness_score"]

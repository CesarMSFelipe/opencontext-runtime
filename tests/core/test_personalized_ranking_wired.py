"""RetrievalPlanner.rank must apply query-personalized graph ranking.

When lexical scores tie, a candidate whose symbol name is mentioned in the query
(and is central in the candidate call graph) must be surfaced ahead of an
unrelated candidate. This pins that the personalized PageRank / identifier
heuristics are actually wired into the live ranking path — and that omitting a
query keeps the ranker backward-compatible.
"""

from __future__ import annotations

from opencontext_core.models.context import ContextItem, ContextPriority
from opencontext_core.retrieval.planner import RetrievalPlanner


class _StubSource:
    name = "stub"

    def __init__(self, items: list[ContextItem]) -> None:
        self._items = items

    def retrieve(self, query: str, limit: int) -> list[ContextItem]:
        return self._items[:limit]


def _graph_item(item_id: str, name: str) -> ContextItem:
    """A graph-symbol candidate carrying the metadata the ranker reads."""
    return ContextItem(
        id=item_id,
        content=f"def {name}(): pass",
        source=f"src/{name}.py:1",
        source_type="graph_symbol",
        priority=ContextPriority.P1,
        tokens=100,
        score=0.5,  # identical lexical score so personalization decides order
        source_trust=0.8,
        metadata={
            "retrieval": {"node": name},
            "graph_provenance": {"file_path": f"src/{name}.py", "line": 1},
            "symbol_kind": "function",
        },
    )


def test_query_mentioned_symbol_ranks_first() -> None:
    # Equal lexical score; only the query mention distinguishes the two.
    unrelated = _graph_item("z_unrelated", "render_widget")
    mentioned = _graph_item("a_authenticate", "authenticate_user")
    planner = RetrievalPlanner([_StubSource([unrelated, mentioned])])

    ranked = planner.rank([unrelated, mentioned], query="authenticate user login")

    assert ranked[0].id == "a_authenticate", "query-personalized ranking not applied"


def test_rank_without_query_is_backward_compatible() -> None:
    # No query => deterministic re-rank identical to the prior behavior.
    a = _graph_item("a", "alpha")
    b = _graph_item("b", "beta")
    planner = RetrievalPlanner([_StubSource([a, b])])

    without_query = [i.id for i in planner.rank([a, b])]
    explicit_none = [i.id for i in planner.rank([a, b], query=None)]

    assert without_query == explicit_none


def test_retrieve_personalizes_with_query() -> None:
    # End-to-end through retrieve(): the query mention must win on a tie.
    unrelated = _graph_item("z_unrelated", "serialize_payload")
    mentioned = _graph_item("a_parse", "parse_manifest")
    planner = RetrievalPlanner([_StubSource([unrelated, mentioned])])

    ranked = planner.retrieve("parse manifest", top_k=5)

    assert ranked[0].id == "a_parse"

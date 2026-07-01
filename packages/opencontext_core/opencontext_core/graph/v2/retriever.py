"""KG v2 retriever — subgraph retrieval with omission tracking.

PR-008.c: SubgraphRetriever executes a KgQueryPlan against the
store and returns a ContextSubgraph with structured omissions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from opencontext_core.graph.v2.planner import KgQueryPlan
from opencontext_core.graph.v2.store import KgStore


@dataclass
class Omission:
    source: str
    reason: str
    tokens_saved: int = 0


@dataclass
class ContextSubgraph:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    omissions: list[Omission] = field(default_factory=list)
    tokens_used: int = 0


class SubgraphRetriever:
    """Execute a query plan and collect the subgraph.

    Tracks omissions so the caller can audit what was left out
    and why (REQ_kg_v2_004).
    """

    def __init__(self, store: KgStore) -> None:
        self._store = store

    def retrieve(self, plan: KgQueryPlan) -> ContextSubgraph:
        nodes: list[dict] = []
        omissions: list[Omission] = []
        for nt in plan.node_types:
            results = self._store.query_nodes_by_type(nt)
            if len(results) > plan.limit:
                omissions.append(
                    Omission(source=nt, reason=f"truncated to {plan.limit}", tokens_saved=len(results) - plan.limit)
                )
                nodes.extend(results[: plan.limit])
            else:
                nodes.extend(results)
        return ContextSubgraph(nodes=nodes, omissions=omissions, tokens_used=len(nodes))


__all__ = ["ContextSubgraph", "Omission", "SubgraphRetriever"]

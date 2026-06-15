"""ProgressiveExpander for OpenContext Runtime v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextItem:
    """A candidate context item for inclusion in a context pack."""

    id: str
    kind: str = "symbol"
    source: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens: int = 0
    source_trust: float = 1.0


EXPANSION_ORDER = ["summary", "symbols", "graph", "files", "lines", "tests", "dependencies"]


class ProgressiveExpander:
    """Expands seed candidates using call graph + memory.

    Stops when all contract.required_symbols are covered OR round_num > plan.expansion_rounds.
    Deduplicates by item.id.
    """

    EXPANSION_ORDER = EXPANSION_ORDER

    def expand(
        self,
        seeds: list[ContextItem],
        plan: Any,
        contract: Any,
        graph: Any = None,
        memory: Any = None,
        round_num: int = 1,
    ) -> list[ContextItem]:
        """One expansion round. Returns enriched candidates."""
        if not seeds:
            return []

        if round_num > plan.expansion_rounds:
            return seeds

        # Check if contract is already satisfied
        required = set(getattr(contract, "required_symbols", []))
        covered = {item.id for item in seeds}
        if required and required.issubset(covered):
            return seeds

        expanded: list[ContextItem] = list(seeds)

        # Expand from graph if available
        if graph is not None:
            for seed in seeds:
                try:
                    neighbors = graph.get_memory_enriched_neighbors(
                        seed.id, radius=plan.graph_radius
                    )
                    for n in neighbors:
                        nid = n.get("id", "")
                        if nid:
                            expanded.append(
                                ContextItem(
                                    id=nid,
                                    kind=n.get("node_kind", "symbol"),
                                    source=n.get("source", ""),
                                )
                            )
                except Exception:
                    pass

        # Expand from memory if available
        if memory is not None and plan.include_memory:
            for seed in seeds:
                try:
                    records = memory.search(seed.id, limit=3)
                    for rec in records:
                        expanded.append(
                            ContextItem(
                                id=getattr(rec, "id", f"mem:{rec}"),
                                kind="memory",
                                source=getattr(rec, "key", ""),
                            )
                        )
                except Exception:
                    pass

        # Deduplicate preserving order
        seen: set[str] = set()
        result: list[ContextItem] = []
        for item in expanded:
            if item.id not in seen:
                seen.add(item.id)
                result.append(item)

        return result

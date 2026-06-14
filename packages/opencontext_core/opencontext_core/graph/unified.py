"""UnifiedGraph: links code graph, memory graph, and execution traces."""

from __future__ import annotations

import hashlib
from typing import Any

from opencontext_core.graph.edges import EdgeKind
from opencontext_core.graph.nodes import NodeKind
from opencontext_core.memory.agent import AgentMemoryStore
from opencontext_core.models.agent_memory import MemoryRecord


def stable_symbol_id(symbol: str) -> str:
    """Deterministic ID for a symbol name (stable across runs)."""
    return hashlib.sha256(symbol.encode()).hexdigest()[:16]


class UnifiedGraph:
    """Single graph that spans code symbols, memory records, and trace events.

    Built on top of existing GraphDatabase (SQLite).
    """

    def __init__(self, graph_db: Any, memory_store: AgentMemoryStore) -> None:
        self._graph = graph_db
        self._memory = memory_store
        # In-memory edge store: (from_id, to_id, edge_kind)
        self._edges: list[dict[str, str]] = []
        # Trace nodes
        self._trace_nodes: list[dict[str, Any]] = []
        # Memory node links: symbol_id → list of memory_ids
        self._memory_links: dict[str, list[tuple[str, str]]] = {}

    def link_memory_to_symbol(
        self, memory_id: str, symbol_id: str, edge_kind: EdgeKind
    ) -> None:
        """Bridge: memory node ↔ code symbol node."""
        self._edges.append(
            {
                "from": memory_id,
                "to": symbol_id,
                "edge_kind": edge_kind.value,
            }
        )
        if symbol_id not in self._memory_links:
            self._memory_links[symbol_id] = []
        self._memory_links[symbol_id].append((memory_id, edge_kind.value))

    def link_failure_to_symbol(
        self, failure_record: MemoryRecord, symbol: str
    ) -> None:
        """Creates BROKE_BEFORE edge from failure pattern to symbol."""
        symbol_id = stable_symbol_id(symbol)
        self.link_memory_to_symbol(
            memory_id=failure_record.id,
            symbol_id=symbol_id,
            edge_kind=EdgeKind.BROKE_BEFORE,
        )

    def add_trace_node(self, trace: dict[str, Any]) -> None:
        """Persist a trace execution node."""
        node = {
            "node_kind": NodeKind.TRACE_RUN.value,
            **trace,
        }
        self._trace_nodes.append(node)

    def get_memory_enriched_neighbors(
        self, symbol: str, radius: int = 2
    ) -> list[dict[str, Any]]:
        """Returns neighbors from code graph PLUS linked memory records as dict nodes.

        Used by ProgressiveExpander for memory-enriched expansion.
        """
        results: list[dict[str, Any]] = []

        # Code graph neighbors (use FTS5 search as proxy for neighbors)
        if self._graph is not None:
            try:
                code_nodes = self._graph.search_fts(symbol, limit=radius * 5)
                for node in code_nodes:
                    results.append(
                        {
                            "id": str(node.get("id", "")),
                            "node_kind": NodeKind.CODE_SYMBOL.value,
                            "name": node.get("name", ""),
                            "source": node.get("file_path", ""),
                        }
                    )
            except Exception:
                pass

        # Memory-linked nodes
        symbol_id = stable_symbol_id(symbol)
        linked = self._memory_links.get(symbol_id, [])
        for memory_id, edge_kind in linked:
            memory_records = self._memory.search(memory_id, limit=1)
            if memory_records:
                rec = memory_records[0]
                results.append(
                    {
                        "id": rec.id,
                        "node_kind": NodeKind.MEMORY_BELIEF.value,
                        "name": rec.key,
                        "source": rec.content[:100],
                        "edge_kind": edge_kind,
                    }
                )
            else:
                results.append(
                    {
                        "id": memory_id,
                        "node_kind": NodeKind.MEMORY_BELIEF.value,
                        "name": "",
                        "source": "",
                        "edge_kind": edge_kind,
                    }
                )

        return results

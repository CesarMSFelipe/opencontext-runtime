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

    def __init__(
        self, graph_db: Any, memory_store: AgentMemoryStore, *, persist: bool = False
    ) -> None:
        self._graph = graph_db
        self._memory = memory_store
        # Persist links/edges across calls via the graph DB connection when asked
        # (and when a graph DB is present). Default off keeps the legacy in-memory
        # behavior so existing callers are unchanged.
        self._persist = bool(persist and graph_db is not None)
        # In-memory edge store: (from_id, to_id, edge_kind)
        self._edges: list[dict[str, str]] = []
        # Trace nodes
        self._trace_nodes: list[dict[str, Any]] = []
        # Memory node links: symbol_id → list of memory_ids
        self._memory_links: dict[str, list[tuple[str, str]]] = {}
        if self._persist:
            self._init_link_table()
            self._load_links()

    def _init_link_table(self) -> None:
        """Create the sidecar link table on the existing graph DB connection.

        Persists UnifiedGraph's memory↔symbol/trace edges (which were in-memory
        only) without altering the GraphDatabase schema module: it reuses the
        live connection and an ``IF NOT EXISTS`` table so a fresh or already-
        provisioned DB is left otherwise untouched.
        """

        try:
            conn = self._graph._connect()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS unified_links (
                    from_id TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    edge_kind TEXT NOT NULL,
                    UNIQUE(from_id, to_id, edge_kind)
                )
                """
            )
            conn.commit()
        except Exception:
            # Persistence is best-effort: degrade to in-memory on any DB error.
            self._persist = False

    def _load_links(self) -> None:
        """Hydrate in-memory link/edge state from the sidecar table."""

        try:
            conn = self._graph._connect()
            rows = conn.execute(
                "SELECT from_id, to_id, edge_kind FROM unified_links ORDER BY from_id, to_id"
            ).fetchall()
        except Exception:
            return
        for row in rows:
            from_id = str(row["from_id"])
            to_id = str(row["to_id"])
            edge_kind = str(row["edge_kind"])
            self._edges.append({"from": from_id, "to": to_id, "edge_kind": edge_kind})
            self._memory_links.setdefault(to_id, []).append((from_id, edge_kind))

    def link_memory_to_symbol(self, memory_id: str, symbol_id: str, edge_kind: EdgeKind) -> None:
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
        if self._persist:
            try:
                conn = self._graph._connect()
                conn.execute(
                    "INSERT OR IGNORE INTO unified_links (from_id, to_id, edge_kind) "
                    "VALUES (?, ?, ?)",
                    (memory_id, symbol_id, edge_kind.value),
                )
                conn.commit()
            except Exception:
                pass

    def link_failure_to_symbol(self, failure_record: MemoryRecord, symbol: str) -> None:
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

    def get_memory_enriched_neighbors(self, symbol: str, radius: int = 2) -> list[dict[str, Any]]:
        """Returns neighbors from code graph PLUS linked memory records as dict nodes.

        Used by ProgressiveExpander for memory-enriched expansion. ``symbol`` may
        be a stable node id or a symbol name: when it resolves to a node in the
        graph DB, true call-graph neighbors (callees + callers) are returned;
        otherwise the FTS5 proxy is used. Results are de-duplicated by id.
        """
        results: list[dict[str, Any]] = []

        # True call-graph neighbors when ``symbol`` resolves to a node id/name.
        if self._graph is not None:
            try:
                results.extend(self._call_graph_neighbors(symbol, radius))
            except Exception:
                pass

        # Code graph neighbors (use FTS5 search as proxy for neighbors)
        if self._graph is not None and not results:
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

        # De-duplicate by id, preserving first-seen order.
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for node in results:
            nid = str(node.get("id", ""))
            if nid and nid not in seen:
                seen.add(nid)
                deduped.append(node)
        return deduped

    def _resolve_node_ids(self, symbol: str) -> list[str]:
        """Resolve ``symbol`` (a stable node id or a name) to graph node id(s)."""

        conn = self._graph._connect()
        # Direct id hit first (stable text ids).
        row = conn.execute("SELECT id FROM nodes WHERE id = ?", (symbol,)).fetchone()
        if row is not None:
            return [str(row["id"])]
        rows = conn.execute("SELECT id FROM nodes WHERE name = ? ORDER BY id", (symbol,)).fetchall()
        return [str(r["id"]) for r in rows]

    def _call_graph_neighbors(self, symbol: str, radius: int) -> list[dict[str, Any]]:
        """Return true callee + caller neighbors for a resolvable symbol/id."""

        from opencontext_core.indexing.call_graph import CallGraphAnalyzer

        node_ids = self._resolve_node_ids(symbol)
        if not node_ids:
            return []
        analyzer = CallGraphAnalyzer(self._graph)
        depth = max(1, radius)
        out: list[dict[str, Any]] = []
        conn = self._graph._connect()
        for node_id in node_ids:
            for neighbor in [
                *analyzer.get_callees(node_id, depth=depth),
                *analyzer.get_callers(node_id, depth=depth),
            ]:
                row = conn.execute(
                    "SELECT id FROM nodes WHERE name = ? AND file_path = ? AND line = ?",
                    (neighbor.get("name"), neighbor.get("file_path"), neighbor.get("line")),
                ).fetchone()
                neighbor_id = str(row["id"]) if row is not None else ""
                if not neighbor_id:
                    continue
                out.append(
                    {
                        "id": neighbor_id,
                        "node_kind": NodeKind.CODE_SYMBOL.value,
                        "name": neighbor.get("name", ""),
                        "source": f"{neighbor.get('file_path', '')}:{neighbor.get('line', '')}",
                    }
                )
        return out

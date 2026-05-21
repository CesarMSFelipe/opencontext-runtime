"""MCP server exposing knowledge graph tools.

Provides tools for AI agents to query the code knowledge graph:
- codegraph_search: Find symbols by name
- codegraph_context: Build relevant context
- codegraph_callers: Find callers
- codegraph_callees: Find callees
- codegraph_impact: Analyze impact
- codegraph_node: Get node details
- codegraph_files: List indexed files
- codegraph_status: Get database stats
"""

from __future__ import annotations

from typing import Any

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.call_graph import CallGraphAnalyzer
from opencontext_core.indexing.graph_db import GraphDatabase
from opencontext_core.indexing.impact_analysis import ImpactAnalyzer
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


class CodeGraphMCPServer:
    """MCP server for knowledge graph tools."""

    def __init__(
        self,
        config: KnowledgeGraphConfig | None = None,
        db_path: str = ".storage/opencontext/codegraph.db",
    ) -> None:
        self.config = config or KnowledgeGraphConfig()
        self.db = GraphDatabase(db_path=db_path)
        self.db.init_schema()
        self.kg = KnowledgeGraph(config=self.config, db_path=db_path)
        self.call_graph = CallGraphAnalyzer(self.db)
        self.impact = ImpactAnalyzer(self.db)

    # Tool implementations

    def codegraph_search(self, query: str, limit: int = 20) -> dict[str, Any]:
        """Search symbols by name."""

        results = self.db.search_fts(query, limit)
        return {
            "query": query,
            "count": len(results),
            "results": results,
        }

    def codegraph_context(self, task: str, max_nodes: int = 20) -> dict[str, Any]:
        """Build relevant code context for a task."""

        # Simple approach: search for task keywords and return top nodes
        results = self.db.search_fts(task, max_nodes)
        return {
            "task": task,
            "count": len(results),
            "nodes": results,
        }

    def codegraph_callers(self, symbol: str, depth: int = 1) -> dict[str, Any]:
        """Find what calls a symbol."""

        # Find node by name
        conn = self.db._connect()
        rows = conn.execute("SELECT id FROM nodes WHERE name = ? LIMIT 1", (symbol,)).fetchall()

        if not rows:
            return {"symbol": symbol, "callers": [], "count": 0}

        node_id = rows[0]["id"]
        callers = self.call_graph.get_callers(node_id, depth)

        return {
            "symbol": symbol,
            "callers": callers,
            "count": len(callers),
        }

    def codegraph_callees(self, symbol: str, depth: int = 1) -> dict[str, Any]:
        """Find what a symbol calls."""

        conn = self.db._connect()
        rows = conn.execute("SELECT id FROM nodes WHERE name = ? LIMIT 1", (symbol,)).fetchall()

        if not rows:
            return {"symbol": symbol, "callees": [], "count": 0}

        node_id = rows[0]["id"]
        callees = self.call_graph.get_callees(node_id, depth)

        return {
            "symbol": symbol,
            "callees": callees,
            "count": len(callees),
        }

    def codegraph_impact(self, symbol: str, depth: int = 2) -> dict[str, Any]:
        """Analyze impact of changing a symbol."""

        conn = self.db._connect()
        rows = conn.execute("SELECT id FROM nodes WHERE name = ?", (symbol,)).fetchall()

        if not rows:
            return {
                "symbol": symbol,
                "affected_files": [],
                "affected_tests": [],
                "direct_callers": [],
                "transitive_dependents": [],
            }

        # Analyze first matching node
        result = self.impact.analyze(rows[0]["id"], depth)

        return {
            "symbol": result.symbol,
            "affected_files": result.affected_files,
            "affected_tests": result.affected_tests,
            "direct_callers": result.direct_callers,
            "transitive_dependents": result.transitive_dependents,
            "depth": result.depth,
        }

    def codegraph_node(self, symbol: str, include_code: bool = True) -> dict[str, Any]:
        """Get details about a specific symbol."""

        conn = self.db._connect()
        rows = conn.execute("SELECT * FROM nodes WHERE name = ? LIMIT 1", (symbol,)).fetchall()

        if not rows:
            return {"symbol": symbol, "found": False}

        row = rows[0]
        return {
            "symbol": symbol,
            "found": True,
            "name": row["name"],
            "kind": row["kind"],
            "file_path": row["file_path"],
            "line": row["line"],
            "language": row["language"],
            "container": row["container"],
            "docstring": row["docstring"],
            "signature": row["signature"],
        }

    def codegraph_files(self) -> dict[str, Any]:
        """Get indexed file structure."""

        conn = self.db._connect()
        rows = conn.execute("SELECT path, language FROM files ORDER BY path").fetchall()

        return {
            "count": len(rows),
            "files": [{"path": r["path"], "language": r["language"]} for r in rows],
        }

    def codegraph_status(self) -> dict[str, Any]:
        """Get index health and statistics."""

        stats = self.db.get_stats()
        return {
            **stats,
            "healthy": True,
        }

    def close(self) -> None:
        self.db.close()
        self.kg.close()

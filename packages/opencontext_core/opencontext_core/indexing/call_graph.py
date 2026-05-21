"""Call graph analysis for tracing callers and callees."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opencontext_core.indexing.graph_db import GraphDatabase


@dataclass
class CallChain:
    """A chain of calls from a starting symbol."""

    start_symbol: str
    depth: int
    chain: list[dict[str, Any]]


class CallGraphAnalyzer:
    """Analyzes call relationships in the knowledge graph."""

    def __init__(self, db: GraphDatabase) -> None:
        self.db = db

    def get_callers(self, node_id: int, depth: int = 1) -> list[dict[str, Any]]:
        """Find all symbols that call the given node.

        Args:
            node_id: Target node ID.
            depth: Maximum traversal depth.

        Returns:
            List of caller dicts with name, file, line, depth.
        """

        results: list[dict[str, Any]] = []
        visited: set[int] = set()
        self._get_callers_recursive(node_id, depth, 1, results, visited)
        return results

    def get_callees(self, node_id: int, depth: int = 1) -> list[dict[str, Any]]:
        """Find all symbols called by the given node.

        Args:
            node_id: Source node ID.
            depth: Maximum traversal depth.

        Returns:
            List of callee dicts with name, file, line, depth.
        """

        results: list[dict[str, Any]] = []
        visited: set[int] = set()
        self._get_callees_recursive(node_id, depth, 1, results, visited)
        return results

    def _get_callers_recursive(
        self,
        node_id: int,
        max_depth: int,
        current_depth: int,
        results: list[dict[str, Any]],
        visited: set[int],
    ) -> None:
        if current_depth > max_depth or node_id in visited:
            return

        visited.add(node_id)

        conn = self.db._connect()
        rows = conn.execute(
            """
            SELECT n.name, n.file_path, n.line, n.kind, e.source_node_id
            FROM edges e
            JOIN nodes n ON e.source_node_id = n.id
            WHERE e.target_node_id = ? AND e.kind = 'calls'
            """,
            (node_id,),
        ).fetchall()

        for row in rows:
            caller_id = row["source_node_id"]
            if caller_id not in visited:
                results.append(
                    {
                        "name": row["name"],
                        "file_path": row["file_path"],
                        "line": row["line"],
                        "kind": row["kind"],
                        "depth": current_depth,
                    }
                )
                self._get_callers_recursive(
                    caller_id, max_depth, current_depth + 1, results, visited
                )

    def _get_callees_recursive(
        self,
        node_id: int,
        max_depth: int,
        current_depth: int,
        results: list[dict[str, Any]],
        visited: set[int],
    ) -> None:
        if current_depth > max_depth or node_id in visited:
            return

        visited.add(node_id)

        conn = self.db._connect()
        rows = conn.execute(
            """
            SELECT n.name, n.file_path, n.line, n.kind, e.target_node_id
            FROM edges e
            JOIN nodes n ON e.target_node_id = n.id
            WHERE e.source_node_id = ? AND e.kind = 'calls'
            """,
            (node_id,),
        ).fetchall()

        for row in rows:
            callee_id = row["target_node_id"]
            if callee_id and callee_id not in visited:
                results.append(
                    {
                        "name": row["name"],
                        "file_path": row["file_path"],
                        "line": row["line"],
                        "kind": row["kind"],
                        "depth": current_depth,
                    }
                )
                self._get_callees_recursive(
                    callee_id, max_depth, current_depth + 1, results, visited
                )

    def get_call_chains(self, start_node_id: int, max_depth: int = 3) -> list[CallChain]:
        """Get all call chains starting from a node.

        Args:
            start_node_id: Starting node ID.
            max_depth: Maximum chain depth.

        Returns:
            List of call chains.
        """

        node = self.db.get_node_by_id(start_node_id)
        if node is None:
            return []

        callees = self.get_callees(start_node_id, max_depth)
        chain = [{"name": node.name, "file_path": node.file_path, "line": node.line}]
        chain.extend(callees)

        return [CallChain(start_symbol=node.name, depth=len(callees), chain=chain)]

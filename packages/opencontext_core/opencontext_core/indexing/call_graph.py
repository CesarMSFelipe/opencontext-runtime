"""Call graph analysis for tracing callers and callees."""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from opencontext_core.indexing.graph_db import GraphDatabase


@dataclass
class PathResult:
    """Result of a BFS path query between two symbols."""

    found: bool
    path: list[dict[str, Any]] = field(default_factory=list)
    depth_exceeded: bool = False
    hops: int = 0


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

    def find_path(
        self,
        source_id: int | str,
        target_id: int | str,
        max_depth: int = 10,
    ) -> PathResult:
        """Find the shortest directed path from source to target using BFS.

        Args:
            source_id: Starting node ID.
            target_id: Target node ID.
            max_depth: Maximum traversal depth (1-50).

        Returns:
            PathResult with path, depth_exceeded, and hop count.
        """

        # Node ids are stable text strings in the DB; normalize so Python-level
        # equality/visited-set checks against DB-returned ids never str/int-mismatch.
        source_id = str(source_id)
        target_id = str(target_id)

        if source_id == target_id:
            source_node = self.db.get_node_by_id(source_id)
            if source_node:
                return PathResult(
                    found=True,
                    path=[
                        {
                            "name": source_node.name,
                            "file_path": source_node.file_path,
                            "line": source_node.line,
                        }
                    ],
                    hops=0,
                )

        visited: set[str] = {source_id}
        queue: deque[tuple[str, list[str]]] = deque()
        queue.append((source_id, [source_id]))
        conn = self.db._connect()
        skipped_due_to_depth = False

        while queue:
            node_id, path = queue.popleft()
            current_depth = len(path) - 1

            if current_depth >= max_depth:
                skipped_due_to_depth = True
                continue

            rows = conn.execute(
                """
                SELECT e.target_node_id
                FROM edges e
                WHERE e.source_node_id = ? AND e.kind = 'calls'
                """,
                (node_id,),
            ).fetchall()

            for row in rows:
                neighbor_id = str(row["target_node_id"])
                if neighbor_id in visited:
                    continue
                if neighbor_id == target_id:
                    full_path_ids = [*path, neighbor_id]
                    hops = len(full_path_ids) - 1
                    full_path = self._ids_to_path(full_path_ids, conn)
                    return PathResult(found=True, path=full_path, hops=hops)

                visited.add(neighbor_id)
                queue.append((neighbor_id, [*path, neighbor_id]))

        return PathResult(found=False, depth_exceeded=skipped_due_to_depth)

    def _ids_to_path(
        self,
        ids: list[str],
        conn: sqlite3.Connection,
    ) -> list[dict[str, Any]]:
        """Convert node IDs to path records with name, file_path, line.

        Ids are stable text strings (hex), so the ORDER BY CASE must bind them as
        parameters — interpolating a raw hex id would be invalid SQL.
        """

        placeholders = ",".join("?" for _ in ids)
        case_clause = " ".join(f"WHEN ? THEN {pos}" for pos in range(len(ids)))
        rows = conn.execute(
            f"""
            SELECT id, name, file_path, line
            FROM nodes
            WHERE id IN ({placeholders})
            ORDER BY CASE id
            {case_clause}
            END
            """,
            [*ids, *ids],
        ).fetchall()
        return [{"name": r["name"], "file_path": r["file_path"], "line": r["line"]} for r in rows]

    def get_callers(self, node_id: int | str, depth: int = 1) -> list[dict[str, Any]]:
        """Find all symbols that call the given node.

        Args:
            node_id: Target node ID.
            depth: Maximum traversal depth.

        Returns:
            List of caller dicts with name, file, line, depth.
        """

        results: list[dict[str, Any]] = []
        visited: set[str] = set()
        self._get_callers_recursive(str(node_id), depth, 1, results, visited)
        return results

    def get_callees(self, node_id: int | str, depth: int = 1) -> list[dict[str, Any]]:
        """Find all symbols called by the given node.

        Args:
            node_id: Source node ID.
            depth: Maximum traversal depth.

        Returns:
            List of callee dicts with name, file, line, depth.
        """

        results: list[dict[str, Any]] = []
        visited: set[str] = set()
        self._get_callees_recursive(str(node_id), depth, 1, results, visited)
        return results

    def _get_callers_recursive(
        self,
        node_id: str,
        max_depth: int,
        current_depth: int,
        results: list[dict[str, Any]],
        visited: set[str],
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
            caller_id = str(row["source_node_id"])
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
        node_id: str,
        max_depth: int,
        current_depth: int,
        results: list[dict[str, Any]],
        visited: set[str],
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
            callee_id = str(row["target_node_id"])
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

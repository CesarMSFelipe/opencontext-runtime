"""Impact analysis for determining what code is affected by a change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opencontext_core.indexing.call_graph import CallGraphAnalyzer
from opencontext_core.indexing.graph_db import GraphDatabase


@dataclass
class ImpactResult:
    """Result of an impact analysis.

    ``found`` distinguishes a real zero-impact symbol (``found=True`` with empty
    caller/dependent lists) from an unknown/missing node (``found=False``), so
    callers never confuse "no impact" with "no such symbol". ``centrality`` and the
    caller/dependent/file/test counts are the risk inputs; ``risk_level`` is derived
    from them (``unknown`` only when the node was not found).
    """

    symbol: str
    direct_callers: list[dict[str, Any]]
    transitive_dependents: list[dict[str, Any]]
    affected_files: list[str]
    affected_tests: list[str]
    depth: int
    found: bool = True
    centrality: int = 0
    risk_level: str = "low"


class ImpactAnalyzer:
    """Analyzes the impact radius of changing a symbol."""

    def __init__(self, db: GraphDatabase) -> None:
        self.db = db
        self.call_graph = CallGraphAnalyzer(db)

    def analyze(
        self,
        node_id: int | str,
        depth: int = 2,
        test_pattern: str | None = None,
    ) -> ImpactResult:
        """Analyze what code is affected by changing a symbol.

        Args:
            node_id: The symbol node ID to analyze.
            depth: Maximum traversal depth for transitive dependents.
            test_pattern: Optional pattern to identify test files.

        Returns:
            Impact analysis result.
        """

        node = self.db.get_node_by_id(node_id)
        if node is None:
            # Unknown node: distinct from a real zero-impact result.
            return ImpactResult(
                symbol="",
                direct_callers=[],
                transitive_dependents=[],
                affected_files=[],
                affected_tests=[],
                depth=0,
                found=False,
                centrality=0,
                risk_level="unknown",
            )

        # Get direct callers (depth 1)
        direct_callers = self.call_graph.get_callers(node_id, depth=1)

        # Get transitive dependents (up to specified depth)
        all_dependents = self.call_graph.get_callers(node_id, depth=depth)

        # Remove direct callers from transitive list
        transitive = [d for d in all_dependents if d["depth"] > 1]

        # Collect affected files
        affected_files = set()
        for caller in all_dependents:
            affected_files.add(caller["file_path"])

        # Identify affected test files (default heuristic when no pattern given).
        affected_tests = [
            f
            for f in affected_files
            if (test_pattern and test_pattern in f)
            or f.startswith("test_")
            or "/test_" in f
            or "_test." in f
            or "/tests/" in f
        ]

        centrality = self._centrality(node_id)
        risk_level = self._risk_level(
            direct=len(direct_callers),
            transitive=len(transitive),
            files=len(affected_files),
            tests=len(affected_tests),
            centrality=centrality,
        )

        return ImpactResult(
            symbol=node.name,
            direct_callers=direct_callers,
            transitive_dependents=transitive,
            affected_files=sorted(affected_files),
            affected_tests=sorted(affected_tests),
            depth=depth,
            found=True,
            centrality=centrality,
            risk_level=risk_level,
        )

    def _centrality(self, node_id: int | str) -> int:
        """In+out degree of a node from the persisted resolved-call edges."""
        conn = self.db._connect()
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM edges WHERE target_node_id = ? AND kind = 'calls')
              + (SELECT COUNT(*) FROM edges WHERE source_node_id = ? AND kind = 'calls')
            """,
            (node_id, node_id),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    @staticmethod
    def _risk_level(
        *, direct: int, transitive: int, files: int, tests: int, centrality: int
    ) -> str:
        """Derive a risk level from the blast-radius inputs.

        A larger affected set and/or higher centrality yields a higher level; a leaf
        with no callers is the lowest defined level (never ``unknown``).
        """
        score = direct + transitive + files + tests + centrality
        if score == 0:
            return "low"
        if score <= 3:
            return "medium"
        if score <= 10:
            return "high"
        return "critical"

    def analyze_by_name(
        self,
        symbol_name: str,
        depth: int = 2,
    ) -> list[ImpactResult]:
        """Analyze impact by symbol name (may match multiple nodes).

        Args:
            symbol_name: Name of the symbol to analyze.
            depth: Maximum traversal depth.

        Returns:
            List of impact results for each matching node.
        """

        conn = self.db._connect()
        rows = conn.execute("SELECT id FROM nodes WHERE name = ?", (symbol_name,)).fetchall()

        return [self.analyze(row["id"], depth) for row in rows]

"""Impact analysis for determining what code is affected by a change."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opencontext_core.indexing.call_graph import CallGraphAnalyzer
from opencontext_core.indexing.graph_db import GraphDatabase


@dataclass
class ImpactResult:
    """Result of an impact analysis."""

    symbol: str
    direct_callers: list[dict[str, Any]]
    transitive_dependents: list[dict[str, Any]]
    affected_files: list[str]
    affected_tests: list[str]
    depth: int


class ImpactAnalyzer:
    """Analyzes the impact radius of changing a symbol."""

    def __init__(self, db: GraphDatabase) -> None:
        self.db = db
        self.call_graph = CallGraphAnalyzer(db)

    def analyze(
        self,
        node_id: int,
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
            return ImpactResult(
                symbol="",
                direct_callers=[],
                transitive_dependents=[],
                affected_files=[],
                affected_tests=[],
                depth=0,
            )

        # Get direct callers (depth 1)
        direct_callers = self.call_graph.get_callers(node_id, depth=1)

        # Get transitive dependents (up to specified depth)
        all_dependents = self.call_graph.get_callers(node_id, depth=depth)

        # Remove direct callers from transitive list
        transitive = [
            d for d in all_dependents
            if d["depth"] > 1
        ]

        # Collect affected files
        affected_files = set()
        for caller in all_dependents:
            affected_files.add(caller["file_path"])

        # Identify affected test files
        affected_tests: list[str] = []
        if test_pattern:
            for f in affected_files:
                if test_pattern in f or f.startswith("test_") or "_test." in f or "/tests/" in f:
                    affected_tests.append(f)

        return ImpactResult(
            symbol=node.name,
            direct_callers=direct_callers,
            transitive_dependents=transitive,
            affected_files=sorted(affected_files),
            affected_tests=sorted(affected_tests),
            depth=depth,
        )

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
        rows = conn.execute(
            "SELECT id FROM nodes WHERE name = ?", (symbol_name,)
        ).fetchall()

        return [self.analyze(row["id"], depth) for row in rows]

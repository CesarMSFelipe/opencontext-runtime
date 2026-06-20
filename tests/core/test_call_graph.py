"""Tests for call graph BFS path finding."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.indexing.call_graph import CallGraphAnalyzer
from opencontext_core.indexing.graph_db import GraphDatabase


def _make_db(path: Path) -> GraphDatabase:
    db = GraphDatabase(db_path=str(path))
    db.init_schema()
    conn = db._connect()
    # Insert test nodes
    conn.executemany(
        "INSERT INTO nodes (id, name, kind, file_path, line, language) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "main", "function", "app.py", 1, "python"),
            (2, "helper", "function", "utils.py", 10, "python"),
            (3, "parse", "function", "parse.py", 5, "python"),
            (4, "validate", "function", "validate.py", 3, "python"),
            (5, "format_output", "function", "format.py", 7, "python"),
            (6, "isolated_func", "function", "isolated.py", 1, "python"),
        ],
    )
    # Insert call edges
    conn.executemany(
        "INSERT INTO edges (source_node_id, target_node_id, kind) VALUES (?, ?, ?)",
        [
            (1, 2, "calls"),  # main -> helper
            (2, 3, "calls"),  # helper -> parse
            (3, 4, "calls"),  # parse -> validate (creates cycle 3->4->3 below)
            (4, 3, "calls"),  # validate -> parse (cycle)
            (2, 5, "calls"),  # helper -> format_output
            (1, 5, "calls"),  # main -> format_output (direct)
        ],
    )
    conn.commit()
    return db


class TestFindPath:
    """Test BFS path finding."""

    def test_direct_edge(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        analyzer = CallGraphAnalyzer(db)
        result = analyzer.find_path(1, 2, max_depth=10)
        assert result.found
        assert len(result.path) == 2
        assert result.path[0]["name"] == "main"
        assert result.path[1]["name"] == "helper"
        assert result.hops == 1
        db.close()

    def test_multi_hop_path(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        analyzer = CallGraphAnalyzer(db)
        result = analyzer.find_path(1, 4, max_depth=10)
        assert result.found
        assert result.hops == 3  # main -> helper -> parse -> validate
        assert result.path[-1]["name"] == "validate"
        db.close()

    def test_no_path(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        analyzer = CallGraphAnalyzer(db)
        # isolated_func (6) has no edges
        result = analyzer.find_path(6, 4, max_depth=10)
        assert not result.found
        assert result.path == []
        db.close()

    def test_same_node(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        analyzer = CallGraphAnalyzer(db)
        result = analyzer.find_path(1, 1, max_depth=10)
        assert result.found
        assert len(result.path) == 1
        assert result.path[0]["name"] == "main"
        assert result.hops == 0
        db.close()

    def test_depth_exceeded(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        analyzer = CallGraphAnalyzer(db)
        # Path is 3 hops: main -> helper -> parse -> validate
        # Limit to max_depth=1 means only 1 hop allowed
        result = analyzer.find_path(1, 4, max_depth=1)
        assert not result.found
        db.close()

    def test_cycle_resilience(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        analyzer = CallGraphAnalyzer(db)
        # There's a cycle: parse (3) -> validate (4) -> parse (3)
        # It should still find the path without infinite loop
        result = analyzer.find_path(1, 4, max_depth=10)
        assert result.found
        assert result.hops == 3
        db.close()

    def test_multiple_paths_shortest_taken(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        analyzer = CallGraphAnalyzer(db)
        # main -> format_output is direct (edge 1->5)
        # main -> helper -> format_output is 2 hops (edges 1->2, 2->5)
        result = analyzer.find_path(1, 5, max_depth=10)
        assert result.found
        assert result.hops == 1  # BFS finds shortest path first
        assert result.path[1]["name"] == "format_output"
        db.close()


class TestCallersCallees:
    """get_callers/get_callees must record minimal depth and expose node ids."""

    def test_callees_record_minimal_depth(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        analyzer = CallGraphAnalyzer(db)
        callees = analyzer.get_callees(1, depth=5)  # main
        by_name = {c["name"]: c["depth"] for c in callees}
        # format_output is a DIRECT callee of main (edge 1->5): depth 1, not 2 via helper.
        assert by_name.get("format_output") == 1
        assert by_name.get("helper") == 1
        assert by_name.get("parse") == 2
        # Each result carries its node id (enables context_builder dedup).
        assert all("id" in c for c in callees)
        db.close()

    def test_callers_record_minimal_depth(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path / "test.db")
        analyzer = CallGraphAnalyzer(db)
        # format_output (5) is called directly by both main (1) and helper (2).
        callers = analyzer.get_callers(5, depth=5)
        by_name = {c["name"]: c["depth"] for c in callers}
        assert by_name.get("main") == 1
        assert by_name.get("helper") == 1
        db.close()

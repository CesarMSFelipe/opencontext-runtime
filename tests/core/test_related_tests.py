"""Related-tests KG query tests (KG_CONTEXT_COMPRESSION_CONTRACT query surface)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.graph.related_tests import find_related_tests
from opencontext_core.indexing.graph_db import Edge, GraphDatabase, Node


@pytest.fixture
def db(tmp_path: Path) -> GraphDatabase:
    graph_db = GraphDatabase(db_path=str(tmp_path / "graph.db"))
    graph_db.init_schema()
    yield graph_db
    graph_db.close()


def _node(name: str, file_path: str, line: int = 1, kind: str = "function") -> Node:
    return Node(
        id=None,
        name=name,
        kind=kind,
        file_path=file_path,
        line=line,
        column=0,
        end_line=line + 5,
        language="python",
        container=None,
        docstring=None,
        signature=f"def {name}()",
        is_exported=True,
    )


def _edge(source_id: str, target_id: str, kind: str, file_path: str) -> Edge:
    return Edge(
        id=None,
        source_node_id=source_id,
        target_node_id=target_id,
        kind=kind,
        call_site_file=file_path,
        call_site_line=3,
    )


def _seed(db: GraphDatabase, edge_kind: str) -> tuple[str, str]:
    """Insert symbol + test nodes connected by an ``edge_kind`` edge."""
    symbol_id = db.insert_node(_node("multiply_values", "calculator.py", line=3))
    test_id = db.insert_node(_node("test_multiply_values", "tests/test_calculator.py", line=8))
    db.insert_edge(_edge(test_id, symbol_id, edge_kind, "tests/test_calculator.py"))
    return symbol_id, test_id


class TestFindRelatedTests:
    def test_symbol_target_finds_test_via_tests_edge(self, db: GraphDatabase) -> None:
        _seed(db, "tests")
        report = find_related_tests(db, "multiply_values")
        assert report["target"] == "multiply_values"
        assert report["resolved"]["matches"] == 1
        tests = report["related_tests"]
        assert [t["test"] for t in tests] == ["test_multiply_values"]
        assert tests[0]["file_path"] == "tests/test_calculator.py"
        assert tests[0]["via"] == "tests"
        assert tests[0]["connected_to"] == "multiply_values"

    def test_covers_edge_kind_is_recognized(self, db: GraphDatabase) -> None:
        _seed(db, "covers")
        report = find_related_tests(db, "multiply_values")
        assert [t["via"] for t in report["related_tests"]] == ["covers"]

    def test_calls_edge_from_test_file_counts_as_test_link(self, db: GraphDatabase) -> None:
        # The indexer emits ``calls`` edges; a call FROM a test file IS the
        # test->symbol relationship until dedicated tests/covers edges land.
        _seed(db, "calls")
        report = find_related_tests(db, "multiply_values")
        assert [t["test"] for t in report["related_tests"]] == ["test_multiply_values"]

    def test_calls_edge_from_non_test_file_is_ignored(self, db: GraphDatabase) -> None:
        symbol_id = db.insert_node(_node("multiply_values", "calculator.py", line=3))
        caller_id = db.insert_node(_node("main", "app.py", line=1))
        db.insert_edge(_edge(caller_id, symbol_id, "calls", "app.py"))
        report = find_related_tests(db, "multiply_values")
        assert report["related_tests"] == []

    def test_file_target_resolves_all_file_symbols(self, db: GraphDatabase) -> None:
        _seed(db, "calls")
        report = find_related_tests(db, "calculator.py")
        assert report["resolved"]["kind"] == "file"
        assert [t["test"] for t in report["related_tests"]] == ["test_multiply_values"]

    def test_unknown_target_reports_zero_matches(self, db: GraphDatabase) -> None:
        report = find_related_tests(db, "no_such_symbol")
        assert report["resolved"]["matches"] == 0
        assert report["related_tests"] == []

    def test_duplicate_edges_are_deduplicated(self, db: GraphDatabase) -> None:
        symbol_id, test_id = _seed(db, "calls")
        db.insert_edge(_edge(test_id, symbol_id, "calls", "tests/test_calculator.py"))
        report = find_related_tests(db, "multiply_values")
        assert len(report["related_tests"]) == 1

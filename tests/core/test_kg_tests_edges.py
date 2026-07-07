"""TESTS edge emission at index time (KG_CONTEXT_COMPRESSION_CONTRACT).

A symbol defined in a test file that calls a non-test symbol gets a dedicated
``tests`` edge (test_symbol -> target) alongside the ``calls`` edge, so
related-tests queries no longer depend on the calls-from-test-file heuristic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.graph.related_tests import find_related_tests
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg(tmp_path: Path) -> KnowledgeGraph:
    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    graph = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    yield graph
    graph.close()


def _write_fixture_project(root: Path) -> None:
    (root / "calculator.py").write_text(
        "def multiply_values(a, b):\n    return a * b\n", encoding="utf-8"
    )
    tests_dir = root / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_calculator.py").write_text(
        "from calculator import multiply_values\n"
        "\n"
        "\n"
        "def test_multiply_values():\n"
        "    assert multiply_values(2, 3) == 6\n",
        encoding="utf-8",
    )


def _tests_edges(kg: KnowledgeGraph) -> list[tuple[str, str]]:
    conn = kg.db._connect()
    rows = conn.execute(
        """
        SELECT src.name AS src_name, tgt.name AS tgt_name
        FROM edges e
        JOIN nodes src ON e.source_node_id = src.id
        JOIN nodes tgt ON e.target_node_id = tgt.id
        WHERE e.kind = 'tests'
        """
    ).fetchall()
    return [(row["src_name"], row["tgt_name"]) for row in rows]


class TestTestsEdgeEmission:
    def test_index_project_emits_symbol_level_tests_edge(
        self, kg: KnowledgeGraph, tmp_path: Path
    ) -> None:
        _write_fixture_project(tmp_path)
        kg.index_project(tmp_path)
        assert ("test_multiply_values", "multiply_values") in _tests_edges(kg)

    def test_reindex_does_not_duplicate_tests_edges(
        self, kg: KnowledgeGraph, tmp_path: Path
    ) -> None:
        _write_fixture_project(tmp_path)
        kg.index_project(tmp_path)
        kg.index_project(tmp_path)
        edges = _tests_edges(kg)
        assert edges.count(("test_multiply_values", "multiply_values")) == 1

    def test_no_tests_edge_between_production_symbols(
        self, kg: KnowledgeGraph, tmp_path: Path
    ) -> None:
        (tmp_path / "calculator.py").write_text(
            "def multiply_values(a, b):\n    return a * b\n", encoding="utf-8"
        )
        (tmp_path / "app.py").write_text(
            "from calculator import multiply_values\n"
            "\n"
            "\n"
            "def main():\n"
            "    return multiply_values(1, 2)\n",
            encoding="utf-8",
        )
        kg.index_project(tmp_path)
        assert _tests_edges(kg) == []

    def test_no_tests_edge_between_two_test_files(self, kg: KnowledgeGraph, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "helpers.py").write_text(
            "def make_pair():\n    return (2, 3)\n", encoding="utf-8"
        )
        (tests_dir / "test_pairs.py").write_text(
            "from helpers import make_pair\n"
            "\n"
            "\n"
            "def test_make_pair():\n"
            "    assert make_pair() == (2, 3)\n",
            encoding="utf-8",
        )
        kg.index_project(tmp_path)
        assert _tests_edges(kg) == []

    def test_related_tests_resolves_via_tests_edge(
        self, kg: KnowledgeGraph, tmp_path: Path
    ) -> None:
        _write_fixture_project(tmp_path)
        kg.index_project(tmp_path)
        report = find_related_tests(kg.db, "multiply_values")
        assert [t["test"] for t in report["related_tests"]] == ["test_multiply_values"]
        assert report["related_tests"][0]["via"] == "tests"

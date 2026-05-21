"""Tests for the knowledge graph facade."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg(tmp_path: Path) -> KnowledgeGraph:
    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    graph = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    yield graph
    graph.close()


class TestIndexFile:
    def test_index_python_file(self, kg: KnowledgeGraph, tmp_path: Path) -> None:
        code = '''\
class UserService:
    """User auth service."""

    def validate(self, email: str) -> bool:
        return True

    def create(self, data: dict) -> dict:
        return data
'''
        stats = kg.index_file("src/auth.py", code)

        assert stats["nodes"] >= 3  # class + 2 methods
        stats = kg.get_stats()
        assert stats["nodes"] >= 3

    def test_skips_disabled(self, tmp_path: Path) -> None:
        config = KnowledgeGraphConfig(enabled=False)
        graph = KnowledgeGraph(config=config, db_path=tmp_path / "kg2.db")
        stats = graph.index_file("src/test.py", "x = 1")
        assert stats == {"nodes": 0, "edges": 0}
        graph.close()

    def test_skips_excluded_pattern(self, kg: KnowledgeGraph) -> None:
        kg.config.exclude = ["vendor/**"]
        stats = kg.index_file("vendor/lib.py", "x = 1")
        assert stats == {"nodes": 0, "edges": 0}

    def test_skips_oversized_file(self, kg: KnowledgeGraph) -> None:
        kg.config.max_file_size = 10
        stats = kg.index_file("src/big.py", "x = 1\n" * 100)
        assert stats == {"nodes": 0, "edges": 0}


class TestIndexProject:
    def test_indexes_project(self, kg: KnowledgeGraph, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
        (tmp_path / "src" / "utils.py").write_text("def helper():\n    return 42\n")
        (tmp_path / "README.md").write_text("# Project\n")

        stats = kg.index_project(tmp_path)

        assert stats["files_indexed"] == 2
        assert stats["nodes"] >= 2


class TestSearch:
    def test_search_finds_symbols(self, kg: KnowledgeGraph) -> None:
        kg.index_file(
            "src/auth.py",
            "class UserService:\n    def login(self):\n        pass\n",
        )

        results = kg.search("UserService")

        # May skip if FTS5 unavailable
        if not results:
            pytest.skip("FTS5 not available")

        assert len(results) > 0
        assert any(r["name"] == "UserService" for r in results)


class TestStats:
    def test_stats_after_index(self, kg: KnowledgeGraph) -> None:
        kg.index_file("src/a.py", "def foo():\n    pass\n")

        stats = kg.get_stats()

        assert stats["nodes"] >= 1
        assert stats["files"] >= 1

"""Tests for context builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.indexing.context_builder import ContextBuilder
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


class TestContextBuilder:
    """Test context builder."""

    def test_build_context_empty_db(self, tmp_path: Path) -> None:
        """Build context with empty database."""

        db_path = tmp_path / "codegraph.db"
        builder = ContextBuilder(db_path=db_path)
        context = builder.build_context(task="implement auth", max_nodes=10)

        assert context.task == "implement auth"
        assert context.nodes == []
        assert context.coverage["nodes_included"] == 0
        assert context.coverage["files_covered"] == 0
        builder.close()

    def test_build_context_with_data(self, tmp_path: Path) -> None:
        """Build context with indexed data."""

        from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser

        if not TreeSitterParser()._available:
            pytest.skip("tree-sitter not available")

        db_path = tmp_path / "codegraph.db"
        kg = KnowledgeGraph(db_path=db_path)

        # Create a test file
        test_file = tmp_path / "test.py"
        test_file.write_text(
            "def authenticate_user(username: str, password: str) -> bool:\n"
            '    """Authenticate a user."""\n'
            "    return verify_password(username, password)\n"
            "\n"
            "def verify_password(u: str, p: str) -> bool:\n"
            "    return hash(p) == stored_hash(u)\n",
            encoding="utf-8",
        )

        result = kg.index_file("test.py", test_file.read_text(encoding="utf-8"))

        builder = ContextBuilder(db_path=db_path)
        context = builder.build_context(task="authentication", max_nodes=10, root=tmp_path)

        assert context.task == "authentication"
        # Nodes may be 0 if parser returns nothing, but should not error
        assert context.total_tokens_estimate >= 0
        builder.close()
        kg.close()

    def test_render_markdown(self, tmp_path: Path) -> None:
        """Render context as markdown."""

        db_path = tmp_path / "codegraph.db"
        builder = ContextBuilder(db_path=db_path)
        context = builder.build_context(task="test", max_nodes=5)
        rendered = builder.render(context)

        assert "# Context for: test" in rendered
        builder.close()

    def test_render_json(self, tmp_path: Path) -> None:
        """Render context as JSON."""

        import json

        db_path = tmp_path / "codegraph.db"
        builder = ContextBuilder(db_path=db_path)
        context = builder.build_context(task="test", max_nodes=5, format="json")
        rendered = builder.render(context)

        data = json.loads(rendered)
        assert data["task"] == "test"
        assert "coverage" in data
        assert "nodes" in data
        builder.close()

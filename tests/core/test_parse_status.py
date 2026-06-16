"""Multi-language parse status (tree-sitter vs regex fallback).

A file whose language has no loaded tree-sitter grammar must report a DEGRADED /
fallback status rather than silently presenting regex-fallback output as a
successful precise parse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser


def test_python_reports_tree_sitter_mode() -> None:
    parser = TreeSitterParser()
    if "python" not in parser._languages:
        pytest.skip("tree-sitter python grammar not installed")
    result = parser.parse_file_status("a.py", "def foo():\n    return bar()\n")
    assert result.mode == "tree_sitter"
    assert result.degraded is False
    # A function that calls another function yields non-empty edges in precise mode.
    assert len(result.edges) >= 1


def test_no_grammar_language_reports_degraded() -> None:
    parser = TreeSitterParser()
    # Ruby grammar is not installed in this environment -> regex fallback / degraded.
    if "ruby" in parser._languages:
        pytest.skip("ruby grammar is installed; pick an unsupported language")
    result = parser.parse_file_status("a.rb", "def foo\n  bar\nend\n")
    assert result.mode != "tree_sitter"
    assert result.degraded is True


def test_index_file_surfaces_degraded_parse_status(tmp_path: Path) -> None:
    parser = TreeSitterParser()
    if "ruby" in parser._languages:
        pytest.skip("ruby grammar is installed; pick an unsupported language")
    config = KnowledgeGraphConfig(enabled=True, languages=["ruby"])
    kg = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    try:
        stats = kg.index_file("a.rb", "def foo\n  bar\nend\n")
        # The degraded status must be observable in the returned stats,
        # not reported as a normal fully-resolved indexed file.
        assert stats.get("parse_mode") != "tree_sitter"
        assert stats.get("degraded") is True
    finally:
        kg.close()


def test_index_file_supported_language_not_degraded(tmp_path: Path) -> None:
    parser = TreeSitterParser()
    if "python" not in parser._languages:
        pytest.skip("tree-sitter python grammar not installed")
    config = KnowledgeGraphConfig(enabled=True, languages=["python"])
    kg = KnowledgeGraph(config=config, db_path=tmp_path / "kg.db")
    try:
        stats = kg.index_file("a.py", "def foo():\n    return 1\n")
        assert stats.get("parse_mode") == "tree_sitter"
        assert stats.get("degraded") is False
    finally:
        kg.close()

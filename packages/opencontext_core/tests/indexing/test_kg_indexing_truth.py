"""K1/K2/K3 — kg-indexing-truth: TS/JS grammars, honest diagnostics, mtime checkpoint."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from opencontext_core.indexing.project_indexer import (
    _load_checkpoint,
    _save_checkpoint,
)
from opencontext_core.indexing.tree_sitter_parser import TreeSitterParser

# ---------------------------------------------------------------------------
# K1 — TS/JS tree-sitter grammars are available and produce symbols + edges
# ---------------------------------------------------------------------------

_TS_SOURCE = """\
function greet(name: string): string {
    return sayHello(name);
}

function sayHello(s: string): string {
    return "Hello, " + s;
}

class Greeter {
    greet(name: string): string {
        return greet(name);
    }
}
"""

_JS_SOURCE = """\
function add(a, b) {
    return multiply(a, b);
}

function multiply(a, b) {
    return a * b;
}
"""


class TestK1JsTsGrammarsShip:
    """K1: TS/JS grammars must be installed and produce real symbols + edges."""

    def test_typescript_grammar_loaded(self) -> None:
        """TreeSitterParser must load the TypeScript grammar at init."""
        parser = TreeSitterParser()
        assert "typescript" in parser._languages, (
            "TypeScript grammar not loaded — add tree-sitter-typescript to deps"
        )

    def test_javascript_grammar_loaded(self) -> None:
        """TreeSitterParser must load the JavaScript grammar at init."""
        parser = TreeSitterParser()
        assert "javascript" in parser._languages, (
            "JavaScript grammar not loaded — add tree-sitter-javascript to deps"
        )

    def test_typescript_symbols_extracted(self) -> None:
        """Parsing a .ts file returns functions and classes."""
        parser = TreeSitterParser()
        symbols, _ = parser.parse_file("src/greeter.ts", _TS_SOURCE)
        names = {s.name for s in symbols}
        assert "greet" in names, f"Expected 'greet' in symbols, got: {names}"
        assert "sayHello" in names, f"Expected 'sayHello' in symbols, got: {names}"
        assert "Greeter" in names, f"Expected 'Greeter' class in symbols, got: {names}"

    def test_javascript_symbols_extracted(self) -> None:
        """Parsing a .js file returns functions."""
        parser = TreeSitterParser()
        symbols, _ = parser.parse_file("src/math.js", _JS_SOURCE)
        names = {s.name for s in symbols}
        assert "add" in names, f"Expected 'add' in symbols, got: {names}"
        assert "multiply" in names, f"Expected 'multiply' in symbols, got: {names}"

    def test_typescript_call_edges_extracted(self) -> None:
        """Parsing a .ts file with intra-file calls returns at least one edge."""
        parser = TreeSitterParser()
        _, edges = parser.parse_file("src/greeter.ts", _TS_SOURCE)
        assert len(edges) > 0, "Expected at least one call edge from greeter.ts, got none"

    def test_kg_indexes_ts_js_symbols_and_edges(self) -> None:
        """Full KG index of a TS+JS project yields nodes and at least one edge."""
        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

        with tempfile.TemporaryDirectory() as tmp:
            kg = KnowledgeGraph(db_path=Path(tmp) / "test.db", project_id="test")
            ts_stats = kg.index_file("src/greeter.ts", _TS_SOURCE)
            js_stats = kg.index_file("src/math.js", _JS_SOURCE)

            assert ts_stats["parse_mode"] == "tree_sitter", (
                f"TS file parsed in degraded mode: {ts_stats['parse_mode']}"
            )
            assert js_stats["parse_mode"] == "tree_sitter", (
                f"JS file parsed in degraded mode: {js_stats['parse_mode']}"
            )
            assert ts_stats["nodes"] > 0, "TypeScript file produced no KG nodes"
            assert js_stats["nodes"] > 0, "JavaScript file produced no KG nodes"
            total_edges = kg.db.get_stats()["edges"]
            assert total_edges > 0, (
                "No call edges in KG after indexing TS+JS files with intra-file calls"
            )


# ---------------------------------------------------------------------------
# K2 — honest counted-not-parsed diagnostic when grammar fails to load
# ---------------------------------------------------------------------------


class TestK2HonestUnparsedDiagnostic:
    """K2: unparsed_files counter in kg_stats + log warning when grammar unavailable."""

    def test_unparsed_files_counter_in_manifest(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When grammar is unavailable, manifest carries unparsed_files counter."""
        from opencontext_core.config import ProjectIndexConfig
        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
        from opencontext_core.indexing.project_indexer import ProjectIndexer

        # Create a minimal project with a TS and JS file
        project_root = tmp_path / "proj"
        project_root.mkdir()
        (project_root / "hello.ts").write_text("function hello(): void {}\n")
        (project_root / "math.js").write_text("function add(a, b) { return a + b; }\n")

        db_dir = tmp_path / "storage" / ".opencontext"
        db_dir.mkdir(parents=True)
        kg = KnowledgeGraph(db_path=db_dir / "context_graph.db", project_id="test")

        cfg = ProjectIndexConfig(root=str(project_root))

        indexer = ProjectIndexer(cfg, "test-proj", knowledge_graph=kg)

        # Monkeypatch the parser to strip JS/TS grammars so parse falls back to regex
        original_languages = indexer.knowledge_graph.parser._languages.copy()
        stripped = {
            k: v for k, v in original_languages.items() if k not in ("javascript", "typescript")
        }

        logger_name = "opencontext_core.indexing.project_indexer"
        with patch.object(indexer.knowledge_graph.parser, "_languages", stripped):
            with caplog.at_level(logging.WARNING, logger=logger_name):
                manifest = indexer.build_manifest(project_root)

        kg_meta = manifest.metadata.get("knowledge_graph", {})
        unparsed = kg_meta.get("unparsed_files", {})
        assert unparsed, (
            f"Expected unparsed_files in kg_stats when grammars are unavailable, got: {kg_meta}"
        )
        # Should have at least one of typescript or javascript
        assert any(lang in unparsed for lang in ("typescript", "javascript")), (
            f"Expected typescript or javascript in unparsed_files, got: {unparsed}"
        )

        # Confirm warning was logged
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("counted but not parsed" in str(m) for m in warning_messages), (
            f"Expected 'counted but not parsed' warning in logs, got: {warning_messages}"
        )


# ---------------------------------------------------------------------------
# K3 — mtime-aware incremental checkpoint
# ---------------------------------------------------------------------------


class TestK3MtimeCheckpoint:
    """K3: checkpoint evolves to dict[str, float] with legacy fallback."""

    def test_load_checkpoint_empty_returns_empty_dict(self, tmp_path: Path) -> None:
        """Non-existent checkpoint returns empty dict."""
        result = _load_checkpoint(tmp_path / "nonexistent.json")
        assert result == {}, f"Expected empty dict, got: {result}"

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Save/load of mtime dict is lossless."""
        path = tmp_path / "checkpoint.json"
        data: dict[str, float] = {"src/foo.ts": 1_700_000_000.123, "src/bar.js": 1_700_000_001.456}
        _save_checkpoint(path, data)
        result = _load_checkpoint(path)
        assert result == data, f"Roundtrip failed: {result}"

    def test_legacy_list_checkpoint_returns_empty_dict(self, tmp_path: Path) -> None:
        """Legacy list-format checkpoint yields empty dict (forces full reindex)."""
        path = tmp_path / "checkpoint.json"
        path.write_text(json.dumps(["src/old.py", "src/other.py"]), encoding="utf-8")
        result = _load_checkpoint(path)
        assert result == {}, (
            f"Legacy list should parse as empty dict (triggers full reindex), got: {result}"
        )

    def test_changed_file_is_reindexed(self, tmp_path: Path) -> None:
        """A file whose mtime changed since last checkpoint is re-indexed."""
        from opencontext_core.config import ProjectIndexConfig
        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
        from opencontext_core.indexing.project_indexer import ProjectIndexer

        project_root = tmp_path / "proj"
        project_root.mkdir()
        py_file = project_root / "main.py"
        py_file.write_text("def hello(): pass\n")

        db_dir = tmp_path / "storage" / ".opencontext"
        db_dir.mkdir(parents=True)
        kg = KnowledgeGraph(db_path=db_dir / "context_graph.db", project_id="test")

        cfg = ProjectIndexConfig(root=str(project_root))
        indexer = ProjectIndexer(cfg, "test-proj", knowledge_graph=kg)

        # First index
        manifest1 = indexer.build_manifest(project_root)
        kg_meta1 = manifest1.metadata["knowledge_graph"]
        assert kg_meta1.get("skipped_unchanged", 0) == 0, "First index should skip nothing"

        # Second index without changes — file should be skipped
        manifest2 = indexer.build_manifest(project_root)
        kg_meta2 = manifest2.metadata["knowledge_graph"]
        assert kg_meta2.get("skipped_unchanged", 0) > 0, (
            f"Second index should report skipped_unchanged > 0, got: {kg_meta2}"
        )

        # Modify the file and re-index — should be reindexed
        import time

        time.sleep(0.05)  # ensure mtime differs
        py_file.write_text("def hello(): return 42\ndef new_fn(): pass\n")
        # Force mtime update (some filesystems have low mtime resolution)
        py_file.touch()

        manifest3 = indexer.build_manifest(project_root)
        kg_meta3 = manifest3.metadata["knowledge_graph"]
        assert kg_meta3.get("reindexed_changed", 0) >= 1, (
            f"Third index after file change should report reindexed_changed >= 1, got: {kg_meta3}"
        )

    def test_unchanged_files_are_skipped(self, tmp_path: Path) -> None:
        """Unchanged files are skipped on re-index (skipped_unchanged counter)."""
        from opencontext_core.config import ProjectIndexConfig
        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
        from opencontext_core.indexing.project_indexer import ProjectIndexer

        project_root = tmp_path / "proj"
        project_root.mkdir()
        (project_root / "a.py").write_text("def foo(): pass\n")
        (project_root / "b.py").write_text("def bar(): pass\n")

        db_dir = tmp_path / "storage" / ".opencontext"
        db_dir.mkdir(parents=True)
        kg = KnowledgeGraph(db_path=db_dir / "context_graph.db", project_id="test")
        cfg = ProjectIndexConfig(root=str(project_root))
        indexer = ProjectIndexer(cfg, "test-proj", knowledge_graph=kg)

        indexer.build_manifest(project_root)  # first run
        manifest2 = indexer.build_manifest(project_root)  # second run
        kg_meta2 = manifest2.metadata["knowledge_graph"]
        assert kg_meta2.get("skipped_unchanged", 0) >= 2, (
            f"Expected >= 2 skipped_unchanged on second run, got: {kg_meta2}"
        )

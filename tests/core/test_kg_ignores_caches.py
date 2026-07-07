"""KG-005: the knowledge graph never indexes caches/junk under default config.

Pins both the default exclusion vocabularies (DEFAULT_IGNORE_PATTERNS and
KnowledgeGraphConfig.exclude) and the index-time behavior: a project containing
``__pycache__``, ``node_modules`` and ``.git`` directories yields zero nodes and
zero file rows from them.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config import DEFAULT_IGNORE_PATTERNS, KnowledgeGraphConfig
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

_JUNK_DIRS = ("__pycache__", "node_modules", ".git")


def test_default_ignore_patterns_pin_cache_directories() -> None:
    """KG-005: DEFAULT_IGNORE_PATTERNS keeps .git, __pycache__ and node_modules excluded."""
    for junk in _JUNK_DIRS:
        assert junk in DEFAULT_IGNORE_PATTERNS, f"missing default ignore pattern: {junk}"


def test_kg_config_default_exclude_pins_cache_directories() -> None:
    """KG-005: KnowledgeGraphConfig default exclude covers the cache/junk directory globs."""
    exclude = KnowledgeGraphConfig().exclude
    for pattern in ("__pycache__/**", "node_modules/**", ".git/**"):
        assert pattern in exclude, f"missing default KG exclude pattern: {pattern}"


def test_index_project_emits_zero_nodes_from_cache_directories(tmp_path: Path) -> None:
    """KG-005: indexing a project with cache dirs present produces no nodes/files from them."""
    (tmp_path / "app.py").write_text("def real_function():\n    return 1\n", encoding="utf-8")
    junk_sources = {
        "__pycache__/cached.py": "def pycache_junk():\n    return 2\n",
        "node_modules/pkg/mod.py": "def node_modules_junk():\n    return 3\n",
        ".git/hooks/hook.py": "def git_junk():\n    return 4\n",
    }
    for rel, content in junk_sources.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    kg = KnowledgeGraph(
        config=KnowledgeGraphConfig(enabled=True, languages=["python"]),
        db_path=tmp_path / ".storage" / "opencontext" / "context_graph.db",
    )
    try:
        kg.index_project(tmp_path)
        conn = kg.db._connect()
        file_paths = [row[0] for row in conn.execute("SELECT path FROM files").fetchall()]
        node_files = [row[0] for row in conn.execute("SELECT file_path FROM nodes").fetchall()]
        node_names = {row[0] for row in conn.execute("SELECT name FROM nodes").fetchall()}
    finally:
        kg.close()

    assert "app.py" in file_paths
    assert "real_function" in node_names
    for path in [*file_paths, *node_files]:
        top = path.split("/", 1)[0]
        assert top not in _JUNK_DIRS, f"indexed junk path: {path}"
    for junk_name in ("pycache_junk", "node_modules_junk", "git_junk"):
        assert junk_name not in node_names, f"indexed junk symbol: {junk_name}"

from __future__ import annotations

from pathlib import Path

from opencontext_core.config import ProjectIndexConfig
from opencontext_core.indexing.project_indexer import ProjectIndexer


def test_project_indexer_builds_static_dependency_graph(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "auth.py").write_text("from app.policy import Policy\n", encoding="utf-8")
    (tmp_path / "app" / "policy.py").write_text("class Policy:\n    pass\n", encoding="utf-8")
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    manifest = ProjectIndexer(config, "dependency-graph").build_manifest()

    assert manifest.dependency_graph is not None
    edges = {(edge.source, edge.target, edge.kind) for edge in manifest.dependency_graph.edges}
    assert ("app/auth.py", "app/policy.py", "from_import") in edges
    assert manifest.metadata["dependency_graph"]["internal_edges"] >= 1


def test_dependency_graph_resolves_relative_imports(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "auth.py").write_text("from .policy import Policy\n", encoding="utf-8")
    (tmp_path / "app" / "policy.py").write_text("class Policy:\n    pass\n", encoding="utf-8")
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    manifest = ProjectIndexer(config, "dependency-graph").build_manifest()

    edges = {(edge.source, edge.target, edge.kind) for edge in manifest.dependency_graph.edges}
    # Before the fix '.policy' never resolved; now it maps to app/policy.py.
    assert ("app/auth.py", "app/policy.py", "from_import") in edges


def test_dependency_graph_tracks_unresolved_external_imports(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("import requests\n", encoding="utf-8")
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    manifest = ProjectIndexer(config, "dependency-graph").build_manifest()

    assert manifest.dependency_graph is not None
    unresolved = {
        (edge.source, edge.target, edge.kind) for edge in manifest.dependency_graph.unresolved
    }
    assert ("main.py", "requests", "import") in unresolved

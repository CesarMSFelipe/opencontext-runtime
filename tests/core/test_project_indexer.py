from __future__ import annotations

import logging
from pathlib import Path

import pytest

from opencontext_core.config import ProjectIndexConfig
from opencontext_core.indexing.project_indexer import ProjectIndexer
from opencontext_profiles import first_party_profiles


def test_indexing_failure_is_logged_not_silently_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A file that fails to index must be surfaced, not silently dropped.

    Regression: the per-file index loop swallowed every exception with
    ``except: pass``, so a broken parser produced a quietly incomplete graph.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("class A: ...\n", encoding="utf-8")
    (tmp_path / "src" / "bad.py").write_text("class B: ...\n", encoding="utf-8")
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

    real = KnowledgeGraph.index_file

    def flaky(self: KnowledgeGraph, path: str, content: str) -> dict:
        if path.endswith("bad.py"):
            raise RuntimeError("boom parser")
        return real(self, path, content)

    monkeypatch.setattr(KnowledgeGraph, "index_file", flaky)
    kg = KnowledgeGraph(db_path=tmp_path / ".storage" / "opencontext" / "context_graph.db")

    with caplog.at_level(logging.WARNING):
        ProjectIndexer(config, "fail-surfacing", knowledge_graph=kg).build_manifest()

    messages = " ".join(r.message for r in caplog.records)
    assert "bad.py" in messages
    assert "failed to index" in messages


def test_project_indexer_ignores_common_virtualenv_directory(tmp_path: Path) -> None:
    (tmp_path / "venv" / "lib").mkdir(parents=True)
    (tmp_path / "venv" / "lib" / "installed.py").write_text(
        "class Dependency: ...\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("class App: ...\n", encoding="utf-8")
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic")

    manifest = ProjectIndexer(config, "ignore-venv").build_manifest()

    assert [file.path for file in manifest.files] == ["src/app.py"]


def test_project_indexer_extracts_python_and_php_symbols(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "service.py").write_text(
        "class UserService:\n    def authenticate(self):\n        return True\n",
        encoding="utf-8",
    )
    (tmp_path / "AuthController.php").write_text(
        "<?php\nclass AuthController {\n  public function login() {}\n}\n",
        encoding="utf-8",
    )
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    manifest = ProjectIndexer(config, "symbols").build_manifest()

    names = {symbol.name for symbol in manifest.symbols}
    assert {"UserService", "authenticate", "AuthController", "login"} <= names
    assert len(manifest.files) == 2


def test_drupal_profile_detection(tmp_path: Path) -> None:
    (tmp_path / "modules" / "custom").mkdir(parents=True)
    (tmp_path / "modules" / "custom" / "example.info.yml").write_text(
        "name: Example\n",
        encoding="utf-8",
    )
    (tmp_path / "example.module").write_text(
        "<?php\nfunction example_help() {}\n",
        encoding="utf-8",
    )
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    manifest = ProjectIndexer(config, "drupal", profiles=first_party_profiles()).build_manifest()

    assert "drupal" in manifest.technology_profiles
    assert manifest.profile == "drupal"


def test_symfony_profile_detection(tmp_path: Path) -> None:
    (tmp_path / "src" / "Controller").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "src" / "Controller" / "HomeController.php").write_text(
        "<?php\nclass HomeController {}\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "routes.yaml").write_text("home: /home\n", encoding="utf-8")
    (tmp_path / "config" / "services.yaml").write_text("services: {}\n", encoding="utf-8")
    config = ProjectIndexConfig(root=str(tmp_path), profile="generic", ignore=[])

    manifest = ProjectIndexer(config, "symfony", profiles=first_party_profiles()).build_manifest()

    assert "symfony" in manifest.technology_profiles
    assert manifest.profile == "symfony"


def test_kg_extensions_cover_all_kg_languages() -> None:
    # The post-run harness re-index filters changed files by _KG_EXTENSIONS; it must
    # cover every KG language (not just python) so JS/TS/Go/Rust/Java/PHP edits also
    # refresh the graph after a task.
    from opencontext_core.indexing.project_indexer import _KG_EXTENSIONS, _KG_LANGUAGES
    from opencontext_core.indexing.tree_sitter_parser import LANGUAGE_EXTENSIONS

    covered = {LANGUAGE_EXTENSIONS[ext] for ext in _KG_EXTENSIONS}
    assert covered == set(_KG_LANGUAGES)
    assert {".py", ".js", ".ts", ".go", ".rs", ".java", ".php"} <= _KG_EXTENSIONS

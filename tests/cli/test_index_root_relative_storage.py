"""``opencontext index <root>`` persists storage under the root, not under cwd.

Regression: the runtime's default ``storage_path`` is relative
(``.storage/opencontext``), so indexing a project from a *different* working
directory wrote the knowledge graph + manifest under that cwd instead of the
project. A later ``knowledge-graph status`` run from the project then found
nothing. The fix anchors storage to the resolved ``<root>`` argument.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

from opencontext_cli.main import _runtime_for_root


def _sample_project(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )


def _run_index(argv: list[str], cwd: Path, monkeypatch) -> None:
    """Run ``opencontext`` with ``argv`` from ``cwd`` (the bug's trigger)."""
    from opencontext_cli import main as main_mod

    monkeypatch.chdir(cwd)
    # Reset the memoized config-path lookup so it resolves from this cwd.
    monkeypatch.setattr(main_mod, "_config_path_cache", None, raising=False)
    with (
        patch.object(sys, "argv", ["opencontext", *argv]),
        patch("sys.stdout", new_callable=io.StringIO),
        patch("sys.stderr", new_callable=io.StringIO),
    ):
        try:
            main_mod.main()
        except SystemExit as exc:
            assert int(exc.code or 0) == 0


def test_runtime_for_root_anchors_storage_to_root(tmp_path: Path) -> None:
    """``_runtime_for_root`` points storage at ``<root>/.storage/opencontext``."""
    runtime = _runtime_for_root("opencontext.yaml", tmp_path)
    assert runtime.storage_path == tmp_path.resolve() / ".storage" / "opencontext"
    assert runtime.knowledge_graph.db.db_path == (
        tmp_path.resolve() / ".storage" / "opencontext" / "context_graph.db"
    )


def test_index_writes_graph_under_root_not_cwd(tmp_path: Path, monkeypatch) -> None:
    """Indexing from a different cwd writes the graph under the project root."""
    project = tmp_path / "project"
    elsewhere = tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    _sample_project(project)

    _run_index(["index", str(project)], cwd=elsewhere, monkeypatch=monkeypatch)

    root_db = project / ".storage" / "opencontext" / "context_graph.db"
    cwd_db = elsewhere / ".storage" / "opencontext" / "context_graph.db"
    root_manifest = project / ".storage" / "opencontext" / "project_manifest.json"
    assert root_db.exists(), "graph must be persisted under the indexed root"
    assert root_manifest.exists(), "manifest must be persisted under the indexed root"
    assert not cwd_db.exists(), "graph must NOT be written under the working directory"

    # The graph written under the root must be non-empty.
    from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph(db_path=root_db)
    try:
        assert kg.get_stats().get("nodes", 0) > 0
    finally:
        kg.close()


def test_index_dot_from_inside_root_still_works(tmp_path: Path, monkeypatch) -> None:
    """``index .`` keeps working: cwd == root, so storage lands under both."""
    project = tmp_path / "proj"
    project.mkdir()
    _sample_project(project)

    _run_index(["index", "."], cwd=project, monkeypatch=monkeypatch)

    root_db = project / ".storage" / "opencontext" / "context_graph.db"
    assert root_db.exists()

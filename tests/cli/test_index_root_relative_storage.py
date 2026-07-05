"""``opencontext index <root>`` persists storage anchored to the project, not cwd.

Regression: the old default storage_path was relative (.storage/opencontext), so
indexing from a different cwd wrote the KG under that cwd. The fix anchors storage
to the resolved <root>. In user mode (default), storage goes to the XDG state dir;
in local mode (OPENCONTEXT_STORAGE_MODE=local), it stays under the project root.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

from opencontext_cli.main import _runtime_for_root
from opencontext_core.paths import StorageMode, resolve_storage_path


def _sample_project(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )


def _run_index(argv: list[str], cwd: Path, monkeypatch) -> None:
    """Run ``opencontext`` with ``argv`` from ``cwd`` (the bug's trigger)."""
    from opencontext_cli import main as main_mod

    monkeypatch.chdir(cwd)
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
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


def test_runtime_for_root_anchors_storage_to_user_dir(tmp_path: Path) -> None:
    """In user mode (default), _runtime_for_root points storage at the XDG state dir."""
    runtime = _runtime_for_root("opencontext.yaml", tmp_path)
    expected = resolve_storage_path(tmp_path, StorageMode.user)
    assert runtime.storage_path == expected


def test_runtime_for_root_local_mode_anchors_to_root(tmp_path: Path, monkeypatch) -> None:
    """In local mode, _runtime_for_root points storage at <root>/.storage/opencontext."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
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

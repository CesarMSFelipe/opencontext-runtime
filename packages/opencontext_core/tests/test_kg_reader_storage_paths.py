"""Readers must locate the KG where the active storage mode puts it.

``opencontext index`` writes ``context_graph.db`` via the storage-mode
resolver (user-mode XDG by default, ``OPENCONTEXT_STORAGE_MODE`` override).
Reader surfaces (TUI brand status, graph explorer, CLI commands) must resolve
the SAME path instead of hardcoding the legacy in-repo
``.storage/opencontext`` layout — otherwise a freshly indexed project shows
"KG: not indexed". For unmigrated projects the legacy path is an honest
fallback when the resolved path is missing.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

from opencontext_core.paths import StorageMode, resolve_storage_path

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_GRAPH_SCREEN_PATH = (
    Path(__file__).parent.parent.parent
    / "opencontext_cli"
    / "opencontext_cli"
    / "tui"
    / "screens"
    / "graph.py"
)


def _make_kg_db(db_path: Path) -> None:
    """Create a minimal indexed-KG fixture (nodes/edges/files tables + rows)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, name TEXT, kind TEXT)")
        conn.execute("CREATE TABLE edges (source_node_id TEXT, target_node_id TEXT)")
        conn.execute("CREATE TABLE files (id TEXT)")
        conn.executemany(
            "INSERT INTO nodes VALUES (?, ?, ?)",
            [
                ("n1", "alpha", "function"),
                ("n2", "beta", "function"),
                ("n3", "mod.py", "file"),
            ],
        )
        conn.execute("INSERT INTO edges VALUES ('n1', 'n2')")
        conn.execute("INSERT INTO files VALUES ('f1')")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def user_mode_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project root with user-mode (XDG-style) storage isolated under tmp.

    Deliberately does NOT set ``OPENCONTEXT_STORAGE_MODE``: the default config
    storage mode is already ``user``, and the reader bug only manifests when
    the mode comes from config (the env override flips even readers that pin
    ``StorageMode.local``).
    """
    state_dir = tmp_path / "xdg-state"
    monkeypatch.setattr("platformdirs.user_state_path", lambda app: state_dir / app, raising=True)
    monkeypatch.delenv("OPENCONTEXT_STORAGE_MODE", raising=False)
    root = tmp_path / "project"
    root.mkdir()
    return root


def _user_db(root: Path) -> Path:
    """Where the indexer writes the KG for *root* in user mode."""
    return resolve_storage_path(root, StorageMode.user) / "context_graph.db"


def _legacy_db(root: Path) -> Path:
    return root / ".storage" / "opencontext" / "context_graph.db"


def _load_graph_screen():
    """Load the TUI graph screen module standalone (textual is optional)."""
    name = "opencontext_cli.tui.screens.graph_storage_path_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(_GRAPH_SCREEN_PATH))
    if spec is None or spec.loader is None:
        pytest.skip(f"cannot locate graph screen at {_GRAPH_SCREEN_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except ImportError as exc:  # textual not installed
        del sys.modules[name]
        pytest.skip(f"graph screen import failed: {exc}")
    return mod


# ---------------------------------------------------------------------------
# Shared resolver helper
# ---------------------------------------------------------------------------


class TestResolveActiveStorageFile:
    def test_prefers_resolved_user_mode_path(self, user_mode_root: Path) -> None:
        from opencontext_core.config_resolver import resolve_active_storage_file

        db = _user_db(user_mode_root)
        _make_kg_db(db)
        assert resolve_active_storage_file(user_mode_root, "context_graph.db") == db

    def test_falls_back_to_legacy_layout(self, user_mode_root: Path) -> None:
        from opencontext_core.config_resolver import resolve_active_storage_file

        legacy = _legacy_db(user_mode_root)
        _make_kg_db(legacy)
        assert resolve_active_storage_file(user_mode_root, "context_graph.db") == legacy

    def test_returns_resolved_path_when_missing_everywhere(self, user_mode_root: Path) -> None:
        from opencontext_core.config_resolver import resolve_active_storage_file

        resolved = resolve_active_storage_file(user_mode_root, "context_graph.db")
        assert resolved == _user_db(user_mode_root)
        assert not resolved.exists()


# ---------------------------------------------------------------------------
# TUI brand status line
# ---------------------------------------------------------------------------


class TestBrandStateKgStatus:
    def test_reports_indexed_in_user_mode(self, user_mode_root: Path) -> None:
        from opencontext_core.dx.brand_state import gather_runtime_brand_state

        _make_kg_db(_user_db(user_mode_root))
        state = gather_runtime_brand_state(user_mode_root)
        assert state.kg_status != "not indexed"
        assert state.kg_status.startswith("healthy")
        assert state.symbols == 2

    def test_legacy_layout_still_reported_indexed(self, user_mode_root: Path) -> None:
        from opencontext_core.dx.brand_state import gather_runtime_brand_state

        _make_kg_db(_legacy_db(user_mode_root))
        state = gather_runtime_brand_state(user_mode_root)
        assert state.kg_status.startswith("healthy")

    def test_unindexed_project_reports_not_indexed(self, user_mode_root: Path) -> None:
        from opencontext_core.dx.brand_state import gather_runtime_brand_state

        state = gather_runtime_brand_state(user_mode_root)
        assert state.kg_status == "not indexed"


# ---------------------------------------------------------------------------
# TUI graph explorer data source
# ---------------------------------------------------------------------------


class TestGraphScreenDataSource:
    def test_pick_focus_finds_nodes_in_user_mode(self, user_mode_root: Path) -> None:
        mod = _load_graph_screen()
        _make_kg_db(_user_db(user_mode_root))
        focus = mod.pick_focus(user_mode_root)
        assert focus in {"n1", "n2"}

    def test_load_node_neighbors_in_user_mode(self, user_mode_root: Path) -> None:
        mod = _load_graph_screen()
        _make_kg_db(_user_db(user_mode_root))
        focus, neighbors = mod.load_node_neighbors("n1", root=user_mode_root)
        assert focus is not None
        assert focus.node_id == "n1"
        assert [n.node_id for n in neighbors] == ["n2"]

    def test_pick_focus_legacy_fallback(self, user_mode_root: Path) -> None:
        mod = _load_graph_screen()
        _make_kg_db(_legacy_db(user_mode_root))
        assert mod.pick_focus(user_mode_root) in {"n1", "n2"}


# ---------------------------------------------------------------------------
# Indexer checkpoint co-location
# ---------------------------------------------------------------------------


class TestIndexerCheckpointLocation:
    def test_checkpoint_written_beside_kg_db(self, user_mode_root: Path) -> None:
        """The resume checkpoint must live beside the KG db it checkpoints.

        In user mode the KG db is under XDG; writing the checkpoint into the
        legacy in-repo layout pollutes the repo with a stray ``.storage/``
        directory — the exact thing user mode exists to prevent.
        """
        from opencontext_core.config import ProjectIndexConfig
        from opencontext_core.indexing.knowledge_graph import KnowledgeGraph
        from opencontext_core.indexing.project_indexer import ProjectIndexer

        (user_mode_root / "mod.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
        kg_db = _user_db(user_mode_root)
        kg_db.parent.mkdir(parents=True, exist_ok=True)
        kg = KnowledgeGraph(db_path=kg_db)
        indexer = ProjectIndexer(
            ProjectIndexConfig(root=str(user_mode_root)),
            "proj",
            knowledge_graph=kg,
        )
        indexer.build_manifest()
        assert (kg_db.parent / "index_checkpoint.json").exists()
        assert not (user_mode_root / ".storage").exists()

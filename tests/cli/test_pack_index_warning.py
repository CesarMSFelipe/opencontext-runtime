"""`pack` on an unindexed root must warn instead of silently emitting an empty pack."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from opencontext_cli.main import _missing_index_warnings


def _make_graph_db(storage: Path, node_count: int) -> None:
    storage.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(storage / "context_graph.db")) as conn:
        conn.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, name TEXT)")
        for i in range(node_count):
            conn.execute("INSERT INTO nodes VALUES (?, ?)", (str(i), f"sym{i}"))
        conn.commit()


def test_warns_when_manifest_missing(tmp_path: Path) -> None:
    warnings = _missing_index_warnings(tmp_path / "storage", ".")
    assert warnings, "missing index must produce a warning"
    assert "opencontext index ." in warnings[0]


def test_warns_when_graph_is_empty(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    _make_graph_db(storage, node_count=0)
    (storage / "project_manifest.json").write_text("{}", encoding="utf-8")
    warnings = _missing_index_warnings(storage, "/some/root")
    assert warnings
    assert "opencontext index /some/root" in warnings[0]


def test_silent_when_index_present(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    _make_graph_db(storage, node_count=3)
    (storage / "project_manifest.json").write_text("{}", encoding="utf-8")
    assert _missing_index_warnings(storage, ".") == []

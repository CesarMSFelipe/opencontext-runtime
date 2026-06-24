"""Tests for the AICX lockfile (Workstream N)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from opencontext_core.models.aicx_lock import (
    AICXLockfile,
    build_lockfile,
    load_lockfile,
    verify_lockfile,
    write_lockfile,
)


def test_build_has_schema_version(tmp_path: Path) -> None:
    lock = build_lockfile(tmp_path)
    assert lock.schema_version == "opencontext.aicx_lock.v1"


def test_build_has_core_entries(tmp_path: Path) -> None:
    lock = build_lockfile(tmp_path)
    names = {e.name for e in lock.entries}
    assert {"schemas", "capability_matrix", "graph"} <= names


def test_build_is_deterministic(tmp_path: Path) -> None:
    a = build_lockfile(tmp_path)
    b = build_lockfile(tmp_path)
    assert a.lock_hash == b.lock_hash


def test_lock_hash_present(tmp_path: Path) -> None:
    assert build_lockfile(tmp_path).lock_hash


def test_write_and_load_round_trip(tmp_path: Path) -> None:
    path = write_lockfile(tmp_path)
    assert path.exists()
    loaded = load_lockfile(tmp_path)
    assert loaded.lock_hash == build_lockfile(tmp_path).lock_hash


def test_load_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_lockfile(tmp_path)


def test_verify_not_locked(tmp_path: Path) -> None:
    result = verify_lockfile(tmp_path)
    assert result["ok"] is False
    assert result["error"] == "not_locked"


def test_verify_matches_after_lock(tmp_path: Path) -> None:
    write_lockfile(tmp_path)
    result = verify_lockfile(tmp_path)
    assert result["ok"] is True
    assert result["drifted"] == []


def test_verify_detects_graph_drift(tmp_path: Path) -> None:
    # Lock with no index (graph empty/unavailable), then index a project so the
    # graph entry changes → drift on the "graph" entry.
    write_lockfile(tmp_path)

    from opencontext_core.config import KnowledgeGraphConfig
    from opencontext_core.indexing.knowledge_graph import KnowledgeGraph

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    db_path = tmp_path / ".storage" / "opencontext" / "context_graph.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    kg = KnowledgeGraph(
        config=KnowledgeGraphConfig(enabled=True, languages=["python"]), db_path=db_path
    )
    kg.index_project(tmp_path)
    kg.close()

    result = verify_lockfile(tmp_path)
    assert result["ok"] is False
    assert "graph" in result["drifted"]


def test_lockfile_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        AICXLockfile(entries=[], lock_hash="x", bogus=1)


def test_matches_helper(tmp_path: Path) -> None:
    a = build_lockfile(tmp_path)
    b = build_lockfile(tmp_path)
    assert a.matches(b)

"""Top-level memory lifecycle CLI handlers: compact summary + full purge.

MEM-006 (compact generates a summary) and MEM-007 (purge removes everything)
at the CLI dispatch level (`handle_memory_lifecycle`), which the tool-level
tests in packages/opencontext_memory never exercise.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
from opencontext_memory import MemoryStore, Observation

from opencontext_cli.commands.memory_v2_cmd import (
    handle_memory_lifecycle,
    purge_memory_state,
)
from opencontext_core.memory_usability.context_repository import ContextRepository
from opencontext_core.models.context import DataClassification


def _open_store(root: Path) -> MemoryStore:
    db = root / ".storage" / "opencontext" / "memory_v2.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return MemoryStore.open(db)


def _write(store: MemoryStore, content: str, *, project: str) -> int:
    return store.write(
        Observation(
            session_id="s-1",
            title="Note",
            content=content,
            project=project,
            type="discovery",
        )
    )


def _lifecycle(root: Path, command: str, capsys: Any, **extra: Any) -> dict[str, Any]:
    handle_memory_lifecycle(argparse.Namespace(cwd=str(root), **extra), command)
    return json.loads(capsys.readouterr().out)


def test_compact_generates_a_summary_record(tmp_path: Path, capsys: Any) -> None:
    """MEM-006: `memory compact` generates a summary record for compacted clusters."""
    store = _open_store(tmp_path)
    keeper = _write(store, "The build cache lives under .cache/build.", project=tmp_path.name)
    dup = _write(store, "The build cache lives under .cache/build.", project=tmp_path.name)

    report = _lifecycle(tmp_path, "compact", capsys)

    assert report["compacted_ids"] == [dup]
    summary = report["summary"]
    assert summary is not None, "compact must report the generated summary"
    assert summary["kind"] == "summary"
    assert str(keeper) in summary["content"]
    assert str(dup) in summary["content"]
    # The summary is a real retrievable record in the context repository.
    items = ContextRepository(tmp_path).list_items()
    stored = [i for i in items if i.id == summary["id"]]
    assert stored and stored[0].kind == "summary"


def test_compact_noop_generates_no_summary(tmp_path: Path, capsys: Any) -> None:
    """MEM-006: a no-op compact reports no summary and stores none."""
    store = _open_store(tmp_path)
    _write(store, "Only one note here.", project=tmp_path.name)

    report = _lifecycle(tmp_path, "compact", capsys)

    assert report["compacted_ids"] == []
    assert report["summary"] is None
    assert [i for i in ContextRepository(tmp_path).list_items() if i.kind == "summary"] == []


def test_purge_removes_context_repository_and_store_files(tmp_path: Path, capsys: Any) -> None:
    """MEM-007: `memory purge --yes` removes the v2 store AND the context repository."""
    store = _open_store(tmp_path)
    _write(store, "Observation to purge.", project=tmp_path.name)
    store.close()
    repo = ContextRepository(tmp_path)
    repo.init_layout()
    repo.store(
        "A markdown memory that purge must remove.",
        kind="fact",
        source="test:seed",
        classification=DataClassification.INTERNAL,
    )
    repo_dir = tmp_path / ".opencontext" / "context-repository"
    assert repo_dir.is_dir()

    report = _lifecycle(tmp_path, "purge", capsys, yes=True)

    assert report["purged"] is True
    assert report["observations_removed"] == 1
    assert any(name.endswith("memory_v2.db") for name in report["removed_files"])
    assert any(str(repo_dir) == removed for removed in report["removed_dirs"])
    assert not (tmp_path / ".storage" / "opencontext" / "memory_v2.db").exists()
    assert not repo_dir.exists()


def test_purge_refuses_without_yes(tmp_path: Path) -> None:
    """MEM-007: purge without --yes refuses with exit 2 and removes nothing."""
    store = _open_store(tmp_path)
    _write(store, "Still here.", project=tmp_path.name)
    store.close()
    with pytest.raises(SystemExit) as excinfo:
        handle_memory_lifecycle(argparse.Namespace(cwd=str(tmp_path), yes=False), "purge")
    assert excinfo.value.code == 2
    assert (tmp_path / ".storage" / "opencontext" / "memory_v2.db").exists()


def test_purge_is_idempotent_on_empty_workspace(tmp_path: Path) -> None:
    """MEM-007: purging a workspace with no managed state reports an empty wipe."""
    report = purge_memory_state(tmp_path)
    assert report["purged"] is True
    assert report["removed_files"] == []
    assert report["removed_dirs"] == []

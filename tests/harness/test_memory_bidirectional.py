"""SDD harness memory is bidirectional with the CLI/MCP observations store.

Regressions:
- SDD ExplorePhase recall read only the agent memory.db, never the CLI/MCP
  observations (memory_v2.db) — a user's `memory v2 save` did not inform SDD.
- A harness run harvested to memory.db but never dual-wrote to memory_v2.db, so
  `opencontext memory v2 search` never surfaced harvested runs.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_memory import MemoryStore, mem_save, mem_search

from opencontext_core.harness.phases import _recall_observations
from opencontext_core.paths import StorageMode, resolve_storage_path


def _obs_store(root: Path) -> Path:
    db = resolve_storage_path(root, StorageMode.local) / "memory_v2.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    return db


def test_explore_recall_folds_memory_v2_observations(tmp_path: Path) -> None:
    db = _obs_store(tmp_path)
    mem_save(
        MemoryStore.open(db),
        session_id="s1",
        project=tmp_path.name,
        title="Auth rule",
        content="authentication must use bcrypt for password hashing",
        type="decision",
    )
    block = _recall_observations(tmp_path, "improve authenticate password hashing")
    assert "bcrypt" in block
    assert "[observation]" in block


def test_recall_empty_without_db(tmp_path: Path) -> None:
    assert _recall_observations(tmp_path, "anything at all") == ""


def test_harness_run_dual_writes_observation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    (tmp_path / "auth.py").write_text("def auth(u, p):\n    return u == p\n", encoding="utf-8")
    (tmp_path / "opencontext.yaml").write_text(
        "version: 1\nmemory:\n  enabled: true\n  harvest_after_run: true\n", encoding="utf-8"
    )
    from opencontext_core.harness.runner import HarnessRunner

    HarnessRunner(root=tmp_path).run("sdd", "improve authenticate bcrypt hashing")

    db = resolve_storage_path(tmp_path, StorageMode.local) / "memory_v2.db"
    assert db.is_file(), "harness run did not create memory_v2.db"
    hits = mem_search(MemoryStore.open(db), query="authenticate", limit=20, project=tmp_path.name)
    assert any(h.get("type") == "run" for h in hits), "harvested run not dual-written to memory_v2"

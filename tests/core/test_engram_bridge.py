"""Tests for the co-resident Engram bridge.

Hermetic: a throwaway SQLite stands in for Engram's store and ``subprocess.run``
is captured, so nothing touches a real Engram install. Detection is forced via
``OPENCONTEXT_ENGRAM`` (auto-detection is otherwise suppressed under pytest).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from opencontext_core.backends.factory import BackendFactory
from opencontext_core.config import SecurityMode
from opencontext_core.memory.composite import CompositeMemoryStore
from opencontext_core.memory.engram_bridge import (
    EngramCliClient,
    detect_engram,
    engram_project,
)
from opencontext_core.memory.graph import LocalMemoryStore

_SCHEMA = """
CREATE TABLE observations (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    topic_key TEXT,
    project TEXT,
    deleted_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _seed_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(_SCHEMA)
    con.executemany(
        "INSERT INTO observations (id, type, title, content, topic_key, project, deleted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "session_summary", "ran the pipeline", "did compression work", "k1", "proj", None),
            (2, "architecture", "compression design", "smart crusher notes", "k2", "proj", None),
            (3, "decision", "unrelated topic", "nothing here", "k3", "proj", None),
            (4, "architecture", "compression elsewhere", "other compression", "k4", "other", None),
            (5, "architecture", "deleted compression", "tombstoned", "k5", "proj", "2026-01-01"),
        ],
    )
    con.commit()
    con.close()


def test_detect_respects_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCONTEXT_ENGRAM", "0")
    assert detect_engram() is False
    monkeypatch.setenv("OPENCONTEXT_ENGRAM", "1")
    assert detect_engram() is True


def test_detect_off_under_pytest_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCONTEXT_ENGRAM", raising=False)
    # PYTEST_CURRENT_TEST is set by pytest -> auto-detection suppressed.
    assert detect_engram() is False


def test_project_slug_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCONTEXT_ENGRAM_PROJECT", "my-proj")
    assert engram_project() == "my-proj"


def test_read_maps_types_and_filters_project(tmp_path: Path) -> None:
    db = tmp_path / "engram.db"
    _seed_db(db)
    client = EngramCliClient(db_path=db, project="proj")

    out = client.mem_search(query="compression", limit=10)
    ids = {r["id"] for r in out["results"]}
    # rows 1 and 2 match (project=proj, not deleted); 4 is other project, 5 deleted.
    assert ids == {"1", "2"}
    layers = {r["id"]: r["type"] for r in out["results"]}
    assert layers["1"] == "episodic"  # session_summary -> episodic
    assert layers["2"] == "semantic"  # architecture -> semantic


def test_read_layer_filter(tmp_path: Path) -> None:
    db = tmp_path / "engram.db"
    _seed_db(db)
    client = EngramCliClient(db_path=db, project="proj")

    episodic = client.mem_search(query="compression", type="episodic", limit=10)
    assert [r["id"] for r in episodic["results"]] == ["1"]

    semantic = client.mem_search(query="compression", type="semantic", limit=10)
    assert [r["id"] for r in semantic["results"]] == ["2"]


def test_read_missing_db_returns_empty(tmp_path: Path) -> None:
    client = EngramCliClient(db_path=tmp_path / "nope.db", project="proj")
    assert client.mem_search(query="anything")["results"] == []


def test_save_invokes_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> Any:
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr("opencontext_core.memory.engram_bridge.subprocess.run", fake_run)
    client = EngramCliClient(db_path=tmp_path / "engram.db", project="proj", binary="engram")
    client.mem_save(title="a fact", content="the body", type="semantic")

    cmd = captured["cmd"]
    assert cmd[:4] == ["engram", "save", "a fact", "the body"]
    assert "--type" in cmd and "discovery" in cmd  # semantic -> discovery
    assert "--project" in cmd and "proj" in cmd


def test_save_never_raises_on_missing_binary(tmp_path: Path) -> None:
    client = EngramCliClient(
        db_path=tmp_path / "engram.db", project="proj", binary="definitely-not-a-binary-xyz"
    )
    # No exception, returns a dict.
    assert client.mem_save(title="t", content="c", type="episodic") == {}


def _cfg(provider: str) -> Any:
    return SimpleNamespace(
        memory=SimpleNamespace(enabled=True, provider=provider),
        security=SimpleNamespace(mode=SecurityMode.DEVELOPER),
        project=SimpleNamespace(name="opencontext-runtime"),
    )


def test_factory_auto_couples_when_detected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENCONTEXT_ENGRAM", "1")
    monkeypatch.setenv("OPENCONTEXT_ENGRAM_DB", str(tmp_path / "engram.db"))
    store = BackendFactory.create_memory_store(_cfg("auto"), tmp_path)
    assert isinstance(store, CompositeMemoryStore)


def test_factory_auto_local_when_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENCONTEXT_ENGRAM", "0")
    store = BackendFactory.create_memory_store(_cfg("auto"), tmp_path)
    assert isinstance(store, LocalMemoryStore)


def test_factory_engram_provider_couples_when_detected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENCONTEXT_ENGRAM", "1")
    monkeypatch.setenv("OPENCONTEXT_ENGRAM_DB", str(tmp_path / "engram.db"))
    store = BackendFactory.create_memory_store(_cfg("engram"), tmp_path)
    assert isinstance(store, CompositeMemoryStore)

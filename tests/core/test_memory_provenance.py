"""Tests for memory provenance fields (Workstream G): run_id + provenance."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from opencontext_core.compat import UTC
from opencontext_core.memory.backends import SQLiteMemoryBackend
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord


def _record(**overrides) -> MemoryRecord:
    now = datetime.now(tz=UTC)
    defaults = dict(
        id="rec-1",
        layer=MemoryLayer.SEMANTIC,
        key="auth:jwt",
        content="JWT used for auth",
        decay_policy=DecayPolicy(enabled=True),
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)


# ── model ─────────────────────────────────────────────────────────────────────


def test_provenance_fields_default_none() -> None:
    r = _record()
    assert r.run_id is None
    assert r.provenance is None


def test_provenance_fields_set() -> None:
    r = _record(run_id="run-42", provenance="agent")
    assert r.run_id == "run-42"
    assert r.provenance == "agent"


# ── SQLite persistence round-trip ─────────────────────────────────────────────


def test_provenance_persists_round_trip(tmp_path: Path) -> None:
    backend = SQLiteMemoryBackend(tmp_path / "mem.db")
    backend.store(_record(run_id="run-99", provenance="harvest"))
    loaded = backend.get_by_key("auth:jwt")
    assert len(loaded) == 1
    assert loaded[0].run_id == "run-99"
    assert loaded[0].provenance == "harvest"


def test_provenance_none_persists_as_none(tmp_path: Path) -> None:
    backend = SQLiteMemoryBackend(tmp_path / "mem.db")
    backend.store(_record())
    loaded = backend.get_by_key("auth:jwt")
    assert loaded[0].run_id is None
    assert loaded[0].provenance is None


def test_legacy_db_without_columns_migrates(tmp_path: Path) -> None:
    """A DB created before the provenance columns existed gets them via _migrate."""
    import sqlite3

    db_path = tmp_path / "legacy.db"
    # Minimal legacy table without run_id/provenance.
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE memory_records ("
        "id TEXT PRIMARY KEY, layer TEXT, key TEXT, content TEXT, confidence REAL, "
        "source_refs TEXT, tags TEXT, linked_nodes TEXT, supersedes TEXT, "
        "contradicted_by TEXT, created_at TEXT, updated_at TEXT)"
    )
    conn.commit()
    conn.close()

    # Opening via the backend runs _migrate, adding the columns.
    backend = SQLiteMemoryBackend(db_path)
    backend.store(_record(run_id="run-x", provenance="manual"))
    loaded = backend.get_by_key("auth:jwt")
    assert loaded[0].run_id == "run-x"
    assert loaded[0].provenance == "manual"


# ── MCP save tool ─────────────────────────────────────────────────────────────


def test_mcp_save_accepts_provenance(tmp_path: Path) -> None:
    from opencontext_core.mcp_stdio import MCPServer
    from opencontext_core.memory.graph import LocalMemoryStore

    class _Runtime:
        def __init__(self, store):
            self._v2_memory_store = store

    store = LocalMemoryStore(tmp_path / "memory.db")
    server = MCPServer(db_path=tmp_path / "graph.db", runtime=_Runtime(store))  # type: ignore[arg-type]
    result = server._call_tool(
        "opencontext_memory_save",
        {"content": "fact", "layer": "semantic", "run_id": "run-7", "provenance": "agent"},
    )
    assert "error" not in result, result
    assert result["data"].get("run_id") == "run-7"
    assert result["data"].get("provenance") == "agent"
    server.close()


def test_mcp_save_without_provenance_omits_keys(tmp_path: Path) -> None:
    from opencontext_core.mcp_stdio import MCPServer
    from opencontext_core.memory.graph import LocalMemoryStore

    class _Runtime:
        def __init__(self, store):
            self._v2_memory_store = store

    store = LocalMemoryStore(tmp_path / "memory.db")
    server = MCPServer(db_path=tmp_path / "graph.db", runtime=_Runtime(store))  # type: ignore[arg-type]
    result = server._call_tool("opencontext_memory_save", {"content": "fact"})
    assert "error" not in result, result
    assert "run_id" not in result
    assert "provenance" not in result
    server.close()

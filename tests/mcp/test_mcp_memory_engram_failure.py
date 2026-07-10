"""F3b: a failed Engram write must NOT be reported as a clean Engram success.

When the composite store is wired with a live Engram leg but the actual
``mem_save`` fails (returns ``{"ok": False}``), ``CompositeMemoryStore.write``
transparently falls back to the local store and keeps the memory. That fallback
is correct — but the MCP ``opencontext_memory_save`` result used to still claim
``backend: engram, degraded: false``, hiding the fact that the durable Engram
write never happened.

The store's own doc contract says: "if Engram unreachable, degraded:true". So a
save whose Engram leg failed must surface ``degraded: true`` (and report the
backend it actually landed on — local), not a clean Engram success.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.memory.fake_engram_client import local_store

from opencontext_core.mcp_stdio import MCPServer, _resolve_backend
from opencontext_core.memory.composite import CompositeMemoryStore
from opencontext_core.memory.engram_mcp_store import EngramMemoryStore


class _FailingEngramClient:
    """A live-looking Engram client whose saves never persist.

    ``mem_save`` returns ``{"ok": False}`` (the exact shape the CLI bridge
    returns on a non-zero ``engram save`` exit), so ``EngramMemoryStore.write``
    yields an empty handle and the composite falls back to local.
    """

    def mem_save(self, **kwargs: Any) -> dict[str, Any]:
        return {"ok": False}

    def mem_search(self, **kwargs: Any) -> dict[str, Any]:
        return {"results": []}

    def mem_update(self, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True}


class _FakeRuntime:
    def __init__(self, store: Any) -> None:
        self._v2_memory_store = store


def _failing_composite(tmp_path: Path) -> CompositeMemoryStore:
    engram = EngramMemoryStore(_FailingEngramClient())  # type: ignore[arg-type]
    return CompositeMemoryStore(local=local_store(tmp_path), engram=engram)


def test_resolve_backend_flags_degraded_when_engram_write_failed(tmp_path: Path) -> None:
    """After a failed engram-leg write, backend resolution must not claim a
    clean engram success — it must report degraded (fell back to local)."""
    from datetime import UTC, datetime

    from opencontext_core.models.agent_memory import (
        DecayPolicy,
        MemoryLayer,
        MemoryRecord,
    )

    store = _failing_composite(tmp_path)
    now = datetime.now(UTC)
    record = MemoryRecord(
        id="id-1",
        layer=MemoryLayer.SEMANTIC,
        key="k",
        content="durable fact",
        confidence=1.0,
        decay_policy=DecayPolicy(enabled=True),
        tags=[],
        created_at=now,
        updated_at=now,
    )
    store.write(record)  # engram leg fails -> falls back to local

    backend, degraded = _resolve_backend(store, record.layer.value)
    assert degraded is True, (backend, degraded)
    assert backend == "local", (backend, degraded)


def test_memory_save_tool_reports_degraded_on_engram_failure(tmp_path: Path) -> None:
    """End-to-end through the MCP tool: a semantic save whose Engram write
    failed reports ``degraded: true`` instead of a clean engram success."""
    server = MCPServer(
        db_path=tmp_path / "graph.db",
        runtime=_FakeRuntime(_failing_composite(tmp_path)),  # type: ignore[arg-type]
    )
    result = server._call_tool(
        "opencontext_memory_save",
        {"content": "durable fact", "layer": "semantic", "key": "auth:jwt"},
    )
    data = result["data"]
    assert "error" not in data, data
    # The write still persisted (locally) — an id is returned.
    assert data.get("id")
    # ...but it must NOT be reported as a clean engram success.
    assert not (data.get("backend") == "engram" and data.get("degraded") is False), data
    assert data.get("degraded") is True, data
    server.close()


def test_successful_engram_write_still_reports_clean_success(tmp_path: Path) -> None:
    """No regression: when the engram leg persists, the save is a clean
    engram success (degraded=False)."""
    from typing import Any as _Any

    class _OkEngramClient:
        def mem_save(self, **kwargs: _Any) -> dict[str, _Any]:
            return {"ok": True, "id": "engram-id"}

        def mem_search(self, **kwargs: _Any) -> dict[str, _Any]:
            return {"results": []}

        def mem_update(self, **kwargs: _Any) -> dict[str, _Any]:
            return {"ok": True}

    engram = EngramMemoryStore(_OkEngramClient())  # type: ignore[arg-type]
    store = CompositeMemoryStore(local=local_store(tmp_path), engram=engram)
    server = MCPServer(
        db_path=tmp_path / "graph.db",
        runtime=_FakeRuntime(store),  # type: ignore[arg-type]
    )
    result = server._call_tool(
        "opencontext_memory_save",
        {"content": "durable", "layer": "semantic", "key": "ok:key"},
    )
    data = result["data"]
    assert data.get("backend") == "engram", data
    assert data.get("degraded") is False, data
    server.close()

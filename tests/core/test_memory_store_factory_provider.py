"""Tests for BackendFactory.create_memory_store provider resolution.

Covers: engram provider -> EngramMemoryStore; graceful degradation to
local/null without raising when engram is unavailable; and AIR_GAPPED mode
never issues an MCP/network call (the injected client's call methods are
never invoked).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from opencontext_core.backends.factory import BackendFactory
from opencontext_core.config import SecurityMode
from opencontext_core.memory.agent import AgentMemoryStore, NullAgentMemoryStore
from opencontext_core.memory.composite import CompositeMemoryStore
from opencontext_core.memory.engram_mcp_store import EngramMemoryStore
from opencontext_core.memory.graph import LocalMemoryStore


class RecordingEngramClient:
    """Records every call so tests can assert no MCP call happened."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def mem_save(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("mem_save")
        return {"id": "x"}

    def mem_search(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("mem_search")
        return {"results": []}

    def mem_update(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("mem_update")
        return {"ok": True}


def _cfg(provider: str = "local", *, mode: SecurityMode = SecurityMode.DEVELOPER) -> Any:
    return SimpleNamespace(
        memory=SimpleNamespace(enabled=True, provider=provider),
        security=SimpleNamespace(mode=mode),
    )


def test_provider_engram_returns_engram_store() -> None:
    client = RecordingEngramClient()
    with tempfile.TemporaryDirectory() as tmpdir:
        store = BackendFactory.create_memory_store(
            _cfg("engram"), Path(tmpdir), engram_client=client
        )
    # engram provider now returns CompositeMemoryStore (local + engram routing)
    assert isinstance(store, CompositeMemoryStore)
    assert isinstance(store, AgentMemoryStore)
    assert not isinstance(store, (LocalMemoryStore, NullAgentMemoryStore))
    assert isinstance(store._engram, EngramMemoryStore)


def test_provider_local_returns_local_store() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = BackendFactory.create_memory_store(_cfg("local"), Path(tmpdir))
    assert isinstance(store, LocalMemoryStore)


def test_disabled_returns_null_store() -> None:
    cfg = SimpleNamespace(
        memory=SimpleNamespace(enabled=False),
        security=SimpleNamespace(mode=SecurityMode.DEVELOPER),
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        store = BackendFactory.create_memory_store(cfg, Path(tmpdir))
    assert isinstance(store, NullAgentMemoryStore)


def test_engram_unavailable_degrades_to_local_without_raising() -> None:
    """If building the engram client raises, fall back to local/null — never raise."""

    def _boom() -> Any:
        raise RuntimeError("engram client construction failed")

    with tempfile.TemporaryDirectory() as tmpdir:
        # engram_client is a factory callable that raises
        store = BackendFactory.create_memory_store(
            _cfg("engram"), Path(tmpdir), engram_client=_boom
        )
    # degraded, did not raise
    assert isinstance(store, (LocalMemoryStore, NullAgentMemoryStore))


def test_engram_provider_no_client_degrades_without_raising() -> None:
    """No engram client supplied -> degrade to local rather than raising."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = BackendFactory.create_memory_store(_cfg("engram"), Path(tmpdir))
    assert isinstance(store, (LocalMemoryStore, NullAgentMemoryStore))


def test_air_gapped_never_issues_mcp_call() -> None:
    """In AIR_GAPPED mode, no engram MCP call is ever issued.

    The store is resolved AND exercised (search/write) and the injected
    client's call methods must remain untouched.
    """
    client = RecordingEngramClient()
    with tempfile.TemporaryDirectory() as tmpdir:
        store = BackendFactory.create_memory_store(
            _cfg("engram", mode=SecurityMode.AIR_GAPPED),
            Path(tmpdir),
            engram_client=client,
        )
        # Exercise the store — even doing real work must not reach the client.
        store.search("anything")
        store.failure_boost(["sym"])
    assert client.calls == []

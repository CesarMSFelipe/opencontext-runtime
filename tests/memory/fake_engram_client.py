"""Recording fake Engram client for in-process boundary tests (PR-AHE-007, 7.4).

This module replaces the live Engram transport without contacting any server.
The fake structurally satisfies ``EngramClient`` (memory/engram_mcp_store.py:34)
so ``EngramMemoryStore`` accepts it just like a real adapter.

Surface kept minimal, on purpose:

* ``mem_save`` — captured verbatim into ``calls`` and stored in ``records``.
* ``mem_search`` — captured; replays against ``records`` so routing tests can
  confirm the right layer was queried.
* ``mem_update`` — captured (used by ``EngramMemoryStore.reinforce``/``contradict``).

Everything is in-process: no sockets, no env vars, no subprocesses. This is
what makes the spec scenario "no live Engram server needed" reproducible.

The companion helpers (``local_store`` / ``composite`` /
``engram_routed_layers``) live here too so a test never needs to reach into
the package internals for the layer split — that mapping is the
``CompositeMemoryStore`` routing contract (single source of truth at
``memory/composite.py:21``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.memory.composite import CompositeMemoryStore
from opencontext_core.memory.engram_mcp_store import EngramMemoryStore
from opencontext_core.memory.graph import LocalMemoryStore


class FakeEngramClient:
    """Recording stand-in for a live Engram MCP client.

    Implements the structural ``EngramClient`` Protocol (mem_save / mem_search /
    mem_update) without contacting any Engram server. Every call is captured
    into ``self.calls`` so routing tests can prove which backend received the
    record (task 7.4).
    """

    def __init__(self) -> None:
        # id -> record dict (the minimal shape EngramMemoryStore consumes)
        self.records: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    # ----- EngramClient protocol surface -----
    def mem_save(self, **kwargs: Any) -> Any:
        self.calls.append(("mem_save", dict(kwargs)))
        record_id = str(kwargs.get("id") or kwargs.get("observation_id") or "")
        self.records[record_id] = dict(kwargs)
        return {"ok": True, "id": record_id or "fake-engram-id"}

    def mem_search(self, **kwargs: Any) -> Any:
        self.calls.append(("mem_search", dict(kwargs)))
        query = str(kwargs.get("query", "")).lower()
        results: list[dict[str, Any]] = []
        for record in self.records.values():
            content = str(record.get("content", "")).lower()
            title = str(record.get("title", "")).lower()
            if query and query not in content and query not in title:
                continue
            results.append(dict(record))
        return {"results": results}

    def mem_update(self, **kwargs: Any) -> Any:
        self.calls.append(("mem_update", dict(kwargs)))
        return {"ok": True}


def local_store(tmp_path: Path) -> LocalMemoryStore:
    """A ``LocalMemoryStore`` that writes to the per-test tmp dir."""
    return LocalMemoryStore(tmp_path / "memory.db")


def composite(local: LocalMemoryStore, client: FakeEngramClient) -> CompositeMemoryStore:
    """Wire a ``LocalMemoryStore`` and a fake-injected ``EngramMemoryStore`` into a
    ``CompositeMemoryStore`` matching the live product wiring (composite.py:33)."""
    engram = EngramMemoryStore(client)  # type: ignore[arg-type]
    return CompositeMemoryStore(local=local, engram=engram)


def engram_routed_layers() -> set[str]:
    """Layer values that ``CompositeMemoryStore`` routes to Engram.

    Re-exports composite.py's split (single source of truth) so parametrized
    tests do not duplicate the layer set in two places.
    """
    from opencontext_core.memory.composite import _ENGRAM_LAYERS

    return {layer.value for layer in _ENGRAM_LAYERS}


def local_routed_layers() -> set[str]:
    """Layer values that ``CompositeMemoryStore`` keeps on the local store."""
    from opencontext_core.memory.composite import _LOCAL_LAYERS

    return {layer.value for layer in _LOCAL_LAYERS}

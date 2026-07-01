"""opencontext_memory - SQLite + FTS5 memory store and MCP-style tools.

Public surface (per ``openspec/changes/agentic-parity-engram-gentle/design.md``
§Public Python API). PR2.a exposes the storage primitives only; the 19 tools
and the relation/conflict/project/lifecycle surfaces land in PR2.b-d.

* ``MemoryStore`` - SQLite-backed observation store with FTS5 BM25 search and
  ``topic_key`` upsert. Loads the canonical ``store/schema.sql`` on first open.
* ``WriteQueue`` - per-connection lock + cross-process ``fcntl``/``msvcrt``
  advisory lock to serialise concurrent writers in any host.
"""

from __future__ import annotations

from opencontext_memory.store.sqlite import MemoryStore, Observation, ObservationWriteResult
from opencontext_memory.store.write_queue import WriteQueue

__all__ = [
    "MemoryStore",
    "Observation",
    "ObservationWriteResult",
    "WriteQueue",
]

"""opencontext_memory.store — durable SQLite + FTS5 store.

Modules:

* ``schema.sql`` — canonical DDL (loaded by ``MemoryStore`` on first open).
* ``sqlite.py`` — :class:`MemoryStore` class; write, search, get, delete,
  topic_key upsert, migrations shim.
* ``write_queue.py`` — :class:`WriteQueue`; per-connection in-process lock
  plus ``fcntl`` (POSIX) / lockfile (Windows) cross-process advisory lock.
* ``migrations.py`` — versioned additive migrations (lands in PR2.b).
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

# opencontext-memory

SQLite + FTS5 memory store and 19 MCP-style tools for OpenContext Runtime.

This package is the concrete memory backend the conductor (`opencontext-sdd`)
and the CLI (`opencontext memory v2 …`) read and write through. It is local
only — no network, no cloud sync, no third-party drivers — and rides the
Python 3.12 stdlib `sqlite3` (FTS5 is built-in on the supported versions).

## Public exports

```python
from opencontext_memory import MemoryStore, WriteQueue
```

## Storage shape

The canonical schema lives in
[`opencontext_memory/store/schema.sql`](./opencontext_memory/store/schema.sql)
and is the single source of truth for tables, indices, and the FTS5 virtual
table. `MemoryStore` loads it on first open.

| Table               | Role                                             |
|---------------------|--------------------------------------------------|
| `observations`      | Canonical row store (id, sync_id, …, deleted_at) |
| `observations_fts`  | FTS5 mirror of `observations(title, content)`    |
| `memory_relations`  | 7-verb × 4-status typed relations                |
| `sessions`          | `mem_session_start` / `mem_session_end`          |

## Cross-process safety

Concurrent writers in the same process serialise through a per-connection
lock; concurrent writers across processes serialise through `WriteQueue`,
which uses `fcntl.flock` on POSIX and a `msvcrt`-compatible lockfile on
Windows.

## Mock LLM

The package never makes network calls. The `tests/conftest.py` autouse
fixture asserts no real LLM env vars are set during test execution so future
tool surface inherits the same guarantee.
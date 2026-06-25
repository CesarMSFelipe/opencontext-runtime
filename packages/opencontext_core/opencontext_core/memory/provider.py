"""MemoryProvider Protocol — semantic interface for memory backends.

Defines the contract that all memory backend adapters must satisfy so
agentic phases can depend on the protocol rather than a concrete class.

NOTE: The ``promote()`` method uses layer-transition semantics. Mapping to
``mark_superseded`` on concrete backends is provisional — confirm with the
memory backend owner before wiring a real adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class MemoryRecord:
    """A single memory item with a key, value, and optional tags."""

    key: str
    value: str
    tags: list[str] = field(default_factory=list)


@runtime_checkable
class MemoryProvider(Protocol):
    """Semantic interface for memory backends used by agentic phases."""

    def recall(self, query: str, *, limit: int = 10) -> list[MemoryRecord]:
        """Return memory items relevant to the query."""
        ...

    def save(self, record: MemoryRecord) -> list[str]:
        """Persist a memory record. Returns a list of affected record IDs."""
        ...

    def promote(self, record_id: str, *, layer: str) -> None:
        """Promote a record to a different memory layer."""
        ...

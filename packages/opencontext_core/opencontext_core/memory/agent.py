"""AgentMemoryStore Protocol and NullAgentMemoryStore for OpenContext Runtime v2."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from opencontext_core.models.agent_memory import MemoryLayer, MemoryRecord
from opencontext_core.models.evidence import EvidenceRef


@runtime_checkable
class AgentMemoryStore(Protocol):
    """Port for agent memory. Callers depend only on this Protocol."""

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]: ...

    def write(self, memory: MemoryRecord) -> str: ...

    def reinforce(self, memory_id: str, evidence: EvidenceRef) -> None: ...

    def contradict(self, memory_id: str, evidence: EvidenceRef) -> None: ...

    def decay(self) -> int: ...

    def failure_boost(self, symbols: list[str]) -> dict[str, float]: ...


class NullAgentMemoryStore:
    """Null Object. Used when memory.enabled = False."""

    def search(
        self, query: str, *, scope: MemoryLayer | None = None, limit: int = 10
    ) -> list[MemoryRecord]:
        return []

    def write(self, memory: MemoryRecord) -> str:
        return memory.id

    def reinforce(self, memory_id: str, evidence: EvidenceRef) -> None:
        return

    def contradict(self, memory_id: str, evidence: EvidenceRef) -> None:
        return

    def decay(self) -> int:
        return 0

    def failure_boost(self, symbols: list[str]) -> dict[str, float]:
        return {}

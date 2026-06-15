"""MemoryHarvester: Observer that extracts learning from harness run results."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from opencontext_core.memory.agent import AgentMemoryStore
from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord

if TYPE_CHECKING:
    pass


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _make_record(
    layer: MemoryLayer,
    key: str,
    content: str,
    linked_nodes: list[str] | None = None,
    confidence: float = 0.8,
) -> MemoryRecord:
    now = _now()
    return MemoryRecord(
        id=str(uuid.uuid4()),
        layer=layer,
        key=key,
        content=content,
        confidence=confidence,
        source_refs=[],
        decay_policy=DecayPolicy(enabled=True, half_life_days=90),
        tags=[],
        linked_nodes=linked_nodes or [],
        created_at=now,
        updated_at=now,
    )


class MemoryHarvester:
    """Observer. Called from ArchivePhase after artifact persistence.

    Pattern: Observer — no coupling with HarnessPhase.
    SRP: only harvests, never retrieves.
    """

    def __init__(self, store: AgentMemoryStore) -> None:
        self.store = store

    def harvest(self, result: Any) -> list[MemoryRecord]:
        """Extract learnings from a HarnessRunResult and write to store."""
        records: list[MemoryRecord] = []

        # Always create an episodic record
        task = getattr(result, "task", "unknown")
        run_id = getattr(result, "run_id", "unknown")
        status = getattr(result, "status", "unknown")
        episodic = _make_record(
            layer=MemoryLayer.EPISODIC,
            key=f"episodic:run:{run_id}",
            content=f"Task '{task}' completed with status '{status}'.",
        )
        records.append(episodic)

        # Procedural: learn from failures
        if self._has_test_failures(result):
            procedural = _make_record(
                layer=MemoryLayer.PROCEDURAL,
                key=f"procedural:failure_pattern:{task[:40]}",
                content=(
                    f"Task '{task}' had test failures. Review test coverage before similar tasks."
                ),
                confidence=0.7,
            )
            records.append(procedural)

        # Failure patterns: missing context
        missing = self._extract_missing_context(result)
        if missing:
            failure = _make_record(
                layer=MemoryLayer.FAILURE,
                key=f"failure:missing_context:{task[:40]}",
                content=f"Task '{task}' was missing context: {', '.join(missing)}.",
                linked_nodes=missing,
                confidence=0.9,
            )
            records.append(failure)

        for rec in records:
            self.store.write(rec)

        return records

    def _has_test_failures(self, result: Any) -> bool:
        """Check if any gate with 'test' in the id has failed."""
        gates = getattr(result, "gates", [])
        for gate in gates:
            gate_id = getattr(gate, "id", "") or ""
            status = getattr(gate, "status", None)
            if "test" in gate_id.lower() and str(status).lower() in ("failed", "failure"):
                return True
        # Also check ledgers for error statuses
        ledgers = getattr(result, "ledgers", [])
        for ledger in ledgers:
            ledger_status = getattr(ledger, "status", "") or ""
            if "fail" in str(ledger_status).lower():
                return True
        return False

    def _extract_missing_context(self, result: Any) -> list[str]:
        """Extract symbols/files that were identified as missing from artifacts."""
        missing: list[str] = []
        artifacts = getattr(result, "artifacts", [])
        for artifact in artifacts:
            meta = getattr(artifact, "metadata", {}) or {}
            missing_ctx = meta.get("missing_context", [])
            if isinstance(missing_ctx, list):
                missing.extend(missing_ctx)
        return missing

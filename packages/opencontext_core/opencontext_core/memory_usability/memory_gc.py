"""Memory garbage collection and pruning."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.memory_usability.context_repository import ContextRepository


class MemoryGCReport(BaseModel):
    """Memory garbage collection report."""

    model_config = ConfigDict(extra="forbid")

    pruned_ids: list[str] = Field(description="Memory ids moved to archive.")
    reason: str = Field(description="GC policy reason.")


class MemoryGarbageCollector:
    """Prunes expired and superseded memory into archive."""

    def __init__(self, repository: ContextRepository) -> None:
        self.repository = repository

    def run(self, dry_run: bool = False) -> MemoryGCReport:
        """Run safe local garbage collection."""

        if dry_run:
            from datetime import datetime

            from opencontext_core.compat import UTC

            now = datetime.now(tz=UTC)
            candidates = [
                item.id
                for item in self.repository.list_items()
                if (item.valid_until is not None and item.valid_until <= now) or item.superseded_by
            ]
            return MemoryGCReport(pruned_ids=candidates, reason="dry_run_expired_or_superseded")
        pruned = self.repository.prune_expired()
        return MemoryGCReport(pruned_ids=pruned, reason="expired_or_superseded")

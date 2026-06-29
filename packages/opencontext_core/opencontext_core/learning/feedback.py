"""RuntimeFeedback — a typed contract over the runtime feedback substrate.

SPEC DL-004 / DL-012. The capture substrate already exists: ``OperationMetrics``
+ ``FeedbackCollector`` (DB-or-JSONL persistence) and the non-blocking
``feed.record_outcome``. This module adds ONLY the missing typed contract over
it — it introduces no parallel persistence path and no second collector. The
Learning Loop reads ``FeedbackCollector`` and projects each ``OperationMetrics``
into a ``RuntimeFeedback`` via :meth:`RuntimeFeedback.from_metrics`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from opencontext_core.learning.feedback_collector import OperationMetrics


class RuntimeFeedback(BaseModel):
    """A typed, durable view of one runtime operation's measured outcome."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.runtime_feedback.v1"
    operation_id: str
    operation_type: str
    tokens_used: int = 0
    tokens_budgeted: int = 0
    context_items_selected: int = 0
    context_items_omitted: int = 0
    files_consulted: int = 0
    symbols_consulted: int = 0
    duration_ms: float = 0.0
    success: bool | None = None
    failing_gates: list[str] = Field(default_factory=list)

    @classmethod
    def from_metrics(cls, metrics: OperationMetrics) -> RuntimeFeedback:
        """Build a ``RuntimeFeedback`` from a captured ``OperationMetrics``.

        Reads the existing substrate record; constructs no collector. The failing
        gates (recorded in ``metrics.metadata['failing_gates']`` by
        ``record_outcome``) are surfaced as a first-class field.
        """
        failing = metrics.metadata.get("failing_gates", []) if metrics.metadata else []
        return cls(
            operation_id=metrics.operation_id,
            operation_type=metrics.operation_type,
            tokens_used=metrics.tokens_used,
            tokens_budgeted=metrics.tokens_budgeted,
            context_items_selected=metrics.context_items_selected,
            context_items_omitted=metrics.context_items_omitted,
            files_consulted=metrics.files_consulted,
            symbols_consulted=metrics.symbols_consulted,
            duration_ms=metrics.duration_ms,
            success=metrics.success,
            failing_gates=[str(g) for g in failing] if isinstance(failing, list) else [],
        )


__all__ = ["RuntimeFeedback"]

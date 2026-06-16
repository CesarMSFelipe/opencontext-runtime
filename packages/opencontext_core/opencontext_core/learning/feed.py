"""Non-blocking outcome feed for the learning subsystem.

The harness and ``verify_context`` call :func:`record_outcome` to feed every
phase/operation outcome (gate pass/fail, token spend, success) into the live
``LearningOrchestrator`` via ``FeedbackCollector.start_operation`` /
``finish_operation``.

This feed is deliberately NON-BLOCKING: a failure anywhere inside the learning
subsystem MUST NOT change the gate/trust outcome of the operation, and MUST NOT
propagate to the caller. ``record_outcome`` therefore swallows every learning
error and always returns the caller's ``outcome`` value unchanged.
"""

from __future__ import annotations

from typing import Any


def record_outcome[T](
    orchestrator: Any | None,
    *,
    operation_type: str,
    query: str,
    task_type: str | None = None,
    tokens_used: int = 0,
    tokens_budgeted: int = 0,
    context_items_selected: int = 0,
    context_items_omitted: int = 0,
    files_consulted: int = 0,
    symbols_consulted: int = 0,
    success: bool | None = None,
    failing_gates: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    outcome: T = None,  # type: ignore[assignment]
) -> T:
    """Record one operation outcome into the learning subsystem, non-blocking.

    Returns ``outcome`` unchanged. Any exception raised while recording is
    swallowed so the caller's real gate/trust decision is never affected.
    """

    if orchestrator is None:
        return outcome

    try:
        op_id = orchestrator.start_operation(
            operation_type,
            query,
            task_type,
            tokens_budgeted,
        )
        meta: dict[str, Any] = dict(metadata or {})
        if failing_gates:
            meta["failing_gates"] = list(failing_gates)
        orchestrator.finish_operation(
            op_id,
            tokens_used=tokens_used,
            context_items_selected=context_items_selected,
            context_items_omitted=context_items_omitted,
            files_consulted=files_consulted,
            symbols_consulted=symbols_consulted,
            success=success,
            metadata=meta or None,
        )
    except Exception:
        # Learning is best-effort. Never let it change or break the operation.
        return outcome

    return outcome

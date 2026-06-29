"""PR-000.4 RuntimeFeedback contract over OperationMetrics (SPEC DL-004/DL-012)."""

from __future__ import annotations

from opencontext_core.learning.feedback import RuntimeFeedback
from opencontext_core.learning.feedback_collector import OperationMetrics


def test_from_metrics_preserves_core_fields() -> None:
    metrics = OperationMetrics(
        operation_id="op-1",
        operation_type="verify_context",
        query="task",
        tokens_used=1234,
        tokens_budgeted=2000,
        context_items_selected=5,
        context_items_omitted=3,
        files_consulted=4,
        symbols_consulted=9,
        duration_ms=42.0,
        success=True,
        metadata={"failing_gates": ["coverage"]},
    )
    fb = RuntimeFeedback.from_metrics(metrics)
    assert fb.schema_version == "opencontext.runtime_feedback.v1"
    assert fb.tokens_used == 1234
    assert fb.context_items_omitted == 3
    assert fb.success is True
    assert fb.failing_gates == ["coverage"]


def test_from_metrics_handles_missing_metadata() -> None:
    metrics = OperationMetrics(operation_id="op-2", operation_type="ask", query="q")
    fb = RuntimeFeedback.from_metrics(metrics)
    assert fb.failing_gates == []
    assert fb.success is None


def test_no_parallel_collector_is_constructed() -> None:
    # DL-012: RuntimeFeedback is a typed view; it owns no persistence path.
    import inspect

    import opencontext_core.learning.feedback as feedback_mod

    source = inspect.getsource(feedback_mod)
    assert "FeedbackCollector(" not in source
    assert "open(" not in source
    assert ".jsonl" not in source

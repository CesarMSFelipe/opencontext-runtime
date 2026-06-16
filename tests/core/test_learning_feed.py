"""non-blocking learning feed.

The harness and verify_context feed every outcome into LearningOrchestrator via
FeedbackCollector.start/finish_operation. The feed MUST be non-blocking: a
learning failure never changes the gate/trust outcome of the operation.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.learning.feed import record_outcome
from opencontext_core.learning.feedback_collector import FeedbackCollector
from opencontext_core.learning.learning_orchestrator import LearningOrchestrator


def test_record_outcome_persists_metric(tmp_path: Path) -> None:
    """A recorded outcome shows up as an OperationMetrics for that operation."""
    orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=tmp_path / "kg.db")
    record_outcome(
        orch,
        operation_type="explore",
        query="add auth",
        tokens_used=420,
        success=True,
    )
    metrics = orch.feedback.load_metrics()
    assert len(metrics) == 1
    m = metrics[0]
    assert m.operation_type == "explore"
    assert m.query == "add auth"
    assert m.tokens_used == 420
    assert m.success is True


def test_failed_gate_recorded_as_failed_outcome(tmp_path: Path) -> None:
    """A failing gate is observed as success=False with the gate name in metadata."""
    orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=tmp_path / "kg.db")
    record_outcome(
        orch,
        operation_type="verify",
        query="ship feature",
        success=False,
        failing_gates=["coverage"],
    )
    metrics = orch.feedback.load_metrics()
    assert metrics[0].success is False
    assert "coverage" in str(metrics[0].metadata.get("failing_gates", []))


def test_learning_failure_is_non_blocking(tmp_path: Path) -> None:
    """If the learning subsystem raises, the outcome value still flows back."""

    class _Boom:
        def start_operation(self, *a: object, **k: object) -> str:
            raise RuntimeError("start blew up")

        def finish_operation(self, *a: object, **k: object) -> None:
            raise RuntimeError("finish blew up")

    sentinel = {"gate": "passed", "trust": "sufficient"}
    # record_outcome must swallow the learning error and return the caller's
    # outcome unchanged — never propagate the exception.
    result = record_outcome(
        _Boom(),
        operation_type="verify",
        query="q",
        success=True,
        outcome=sentinel,
    )
    assert result is sentinel


def test_record_outcome_none_orchestrator_is_safe(tmp_path: Path) -> None:
    """A missing orchestrator is a no-op, never an error."""
    out = {"ok": True}
    assert record_outcome(None, operation_type="ask", query="q", outcome=out) is out


# ── honest savings (realized vs projected) ───────────────────────────────────


def test_savings_realized_zero_when_nothing_applied(tmp_path: Path) -> None:
    """report_savings() reports realized=0 and labels projected savings."""
    from opencontext_core.learning.token_optimizer import TokenOptimizer

    feedback = FeedbackCollector(storage_path=tmp_path)
    optimizer = TokenOptimizer(feedback, storage_path=tmp_path)
    for _ in range(5):
        op_id = feedback.start_operation("ask", "q", tokens_budgeted=4000)
        feedback.finish_operation(op_id, tokens_used=500, success=True)
    optimizer.optimize_budgets()

    report = optimizer.report_savings()
    # Honesty: nothing applied → realized is explicitly zero.
    assert report["realized_savings_tokens"] == 0
    # Projected savings are present and labeled as projected/potential.
    assert "projected_savings_tokens" in report
    assert report["projected_savings_tokens"] >= 0
    # Backward-compatible key preserved.
    assert "total_potential_savings_tokens" in report


def test_savings_with_no_operations_is_zero(tmp_path: Path) -> None:
    """No recorded operations → all savings figures are zero, not invented."""
    from opencontext_core.learning.token_optimizer import TokenOptimizer

    feedback = FeedbackCollector(storage_path=tmp_path)
    optimizer = TokenOptimizer(feedback, storage_path=tmp_path)
    report = optimizer.report_savings()
    assert report["realized_savings_tokens"] == 0
    assert report["projected_savings_tokens"] == 0


def test_verify_report_exposes_savings_and_gates(tmp_path: Path) -> None:
    """The verification report carries machine-readable savings + per-gate status."""
    from opencontext_core.verification import build_report_payload, run_all_checks

    report = run_all_checks()
    payload = build_report_payload(report)
    assert "savings" in payload
    assert "gates" in payload
    assert isinstance(payload["gates"], list)
    # savings must be honest (zero realized when nothing applied), never absent.
    assert payload["savings"]["realized_savings_tokens"] == 0

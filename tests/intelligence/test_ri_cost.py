"""Cost Engine — estimate, estimate-vs-actual report, cost_by_component (SPEC-RI-011-08)."""

from __future__ import annotations

from opencontext_core.models.intelligence import CostEstimate, CostReport
from opencontext_core.runtime_intelligence.cost import CostEngine


def test_estimate_builds_costestimate_with_assumptions() -> None:
    engine = CostEngine()
    estimate = engine.estimate("add a new feature to the parser", "oc-flow", "fast")
    assert isinstance(estimate, CostEstimate)
    assert estimate.estimated_input_tokens > 0
    assert estimate.estimated_output_tokens > 0
    assert estimate.estimated_tool_calls >= 1
    assert estimate.assumptions  # documents the heuristic, never silent
    # No live provider pricing yet (PR-012) — honest None, not a fabricated cost.
    assert estimate.estimated_cost_usd is None


def test_report_computes_estimate_error_and_token_savings(tmp_path, make_trace) -> None:
    engine = CostEngine()
    estimate = engine.estimate("fix bug", "oc-flow", "fast", root=tmp_path)
    trace = make_trace(input_tokens=estimate.estimated_input_tokens * 2, output_tokens=0)

    report = engine.report(
        session_id="sess_1",
        run_id="run_1",
        estimate=estimate,
        trace=trace,
        root=tmp_path,
        emit=False,
    )
    assert isinstance(report, CostReport)
    # Actual is ~2x estimated input → positive (under)estimate error.
    assert report.estimate_error_pct > 0
    # Token savings reuse the honest whole-project naive baseline.
    assert report.token_savings["optimized"] == report.actual_input_tokens + (
        report.actual_output_tokens
    )
    assert "saved" in report.token_savings
    # cost_by_component is populated from the trace timings (time-share proxy).
    assert report.cost_by_component
    assert "context_retrieval" in report.cost_by_component


def test_report_cost_by_component_prefers_metrics(tmp_path) -> None:
    from opencontext_core.metrics import MetricsCollector

    collector = MetricsCollector(metrics_dir=tmp_path / "metrics")
    op = collector.start("retrieval", component="context_retrieval")
    collector.stop(op, input_tokens=1000, output_tokens=200, provider="openai")

    engine = CostEngine()
    estimate = engine.estimate("fix bug", "oc-flow", "fast", root=tmp_path)
    report = engine.report(
        session_id="s",
        run_id="r",
        estimate=estimate,
        metrics=collector,
        actual_input_tokens=1000,
        actual_output_tokens=200,
        root=tmp_path,
        emit=False,
    )
    assert "context_retrieval" in report.cost_by_component
    assert report.cost_by_component["context_retrieval"] > 0

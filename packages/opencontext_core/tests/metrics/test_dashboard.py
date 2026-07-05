"""Tests for success-metrics-dashboard (PR-R2-G).

REQ-metrics-dash-001..004 — KPI schema + dashboard + CI tracking.
"""

from __future__ import annotations

from datetime import UTC, datetime


class TestMetricCard:
    def test_card_fields(self) -> None:
        from opencontext_core.metrics.dashboard import MetricCard

        card = MetricCard(
            name="task_success_rate",
            value=0.78,
            trend="up",
            threshold=0.65,
        )
        assert card.name == "task_success_rate"
        assert card.value == 0.78
        assert card.trend == "up"
        assert card.threshold == 0.65

    def test_card_below_threshold(self) -> None:
        from opencontext_core.metrics.dashboard import MetricCard

        card = MetricCard(
            name="cache_hit_rate",
            value=0.10,
            trend="down",
            threshold=0.50,
        )
        assert card.is_below_threshold() is True


class TestCollectMetrics:
    def test_collect_all_13_kpis(self) -> None:
        from opencontext_core.metrics.dashboard import MetricsDashboard

        dash = MetricsDashboard()
        cards = dash.collect_metrics(
            {
                "time_to_first_success_minutes": 12.0,
                "task_success_rate": 0.82,
                "tokens_per_task": 4200.0,
                "cache_hit_rate": 0.71,
                "first_pass_yield": 0.65,
                "p50_latency_s": 1.4,
                "p95_latency_s": 6.8,
                "eval_suite_pass_rate": 0.94,
                "redaction_false_positive_rate": 0.02,
                "redaction_false_negative_rate": 0.0,
                "kg_retrieval_mrr": 0.81,
                "memory_usefulness_score": 0.74,
                "compatibility_violations": 0.0,
            }
        )
        assert len(cards) == 13
        names = {c.name for c in cards}
        assert "task_success_rate" in names
        assert "compatibility_violations" in names

    def test_missing_methodology_version_raises(self) -> None:
        from opencontext_core.metrics.dashboard import (
            MetricsDashboard,
            MissingMethodologyError,
        )

        dash = MetricsDashboard()
        try:
            dash.record(
                kpi="task_success_rate",
                value=0.78,
                methodology_version="",
                run_id="r1",
                ts=datetime.now(UTC),
            )
        except MissingMethodologyError:
            return
        raise AssertionError("expected MissingMethodologyError")


class TestRenderDashboard:
    def test_markdown_lists_all_kpis(self) -> None:
        from opencontext_core.metrics.dashboard import MetricsDashboard

        dash = MetricsDashboard()
        sample = {
            k: 0.5
            for k in [
                "time_to_first_success_minutes",
                "task_success_rate",
                "tokens_per_task",
                "cache_hit_rate",
                "first_pass_yield",
                "p50_latency_s",
                "p95_latency_s",
                "eval_suite_pass_rate",
                "redaction_false_positive_rate",
                "redaction_false_negative_rate",
                "kg_retrieval_mrr",
                "memory_usefulness_score",
                "compatibility_violations",
            ]
        }
        output = dash.render_dashboard(sample, format="md")
        assert "task_success_rate" in output
        assert "compatibility_violations" in output
        assert "methodology_version" in output.lower() or "methodology" in output.lower()

    def test_unknown_format_falls_back_to_markdown(self) -> None:
        from opencontext_core.metrics.dashboard import MetricsDashboard

        dash = MetricsDashboard()
        output = dash.render_dashboard({}, format="xml")  # type: ignore[arg-type]
        assert "OpenContext" in output or "dashboard" in output.lower()

    def test_methodology_bump_breaks_sparkline(self) -> None:
        from opencontext_core.metrics.dashboard import MetricsDashboard

        dash = MetricsDashboard()
        snap = dash.build_snapshot(
            records=[
                ("task_success_rate", 0.7, "2026.06.01", "r1"),
                ("task_success_rate", 0.78, "2026.07.01", "r2"),
            ],
        )
        rendered = dash.render_with_methodology(snap)
        # Methodology change annotation should appear
        assert "methodology" in rendered.lower()

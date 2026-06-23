"""Formatting tests for the honest efficiency report.

The fake markdown report (over fabricated ``BenchmarkSuite`` results) was EXCISED.
These tests assert the real CON-vs-SIN report renders per-case cost, deltas, and
aggregates — and crucially carries NO "X% reduction"/badge/claim string (EB-6).
"""

from __future__ import annotations

import re

from opencontext_core.evaluation.efficiency import (
    format_efficiency_report,
    format_efficiency_report_json,
)
from opencontext_core.evaluation.models import (
    CostTriple,
    EfficiencyCaseResult,
    EfficiencyReport,
)

_CLAIM = re.compile(r"%|reduction_pct|\bbadge\b|\bclaim\b|fewer tokens|faster", re.IGNORECASE)


def _report() -> EfficiencyReport:
    return EfficiencyReport(
        cases=[
            EfficiencyCaseResult(
                case_id="simple/case-a",
                difficulty="simple",
                con=CostTriple(tokens=300, tool_calls=1, latency_ms=5.0),
                sin=CostTriple(tokens=1200, tool_calls=7, latency_ms=30.0),
                ceiling_tokens=99999,
                con_sufficient=True,
                source_coverage=1.0,
                forbidden_hits=[],
                reasons=["quality parity met"],
            ),
            EfficiencyCaseResult(
                case_id="hard/case-b",
                difficulty="hard",
                con=CostTriple(tokens=900, tool_calls=1, latency_ms=12.0),
                sin=CostTriple(tokens=900, tool_calls=9, latency_ms=55.0),
                ceiling_tokens=99999,
                con_sufficient=False,
                source_coverage=0.5,
                forbidden_hits=[],
                reasons=["source coverage 0.50 below required 1.00"],
            ),
        ]
    )


class TestEfficiencyReportText:
    def test_contains_per_case_cost(self) -> None:
        text = format_efficiency_report(_report())
        assert "simple/case-a" in text
        assert "hard/case-b" in text
        # CON and SIN token columns appear.
        assert "300" in text and "1200" in text

    def test_marks_insufficient_parity(self) -> None:
        text = format_efficiency_report(_report())
        assert "INSUFF" in text  # the parity-failing case is flagged, not counted a win
        assert "1 parity-insufficient" in text

    def test_reports_aggregates(self) -> None:
        text = format_efficiency_report(_report())
        assert "median token delta" in text
        assert "latency p50 / p95" in text

    def test_no_baked_claim(self) -> None:
        text = format_efficiency_report(_report())
        assert not _CLAIM.search(text), f"claim-like token in report:\n{text}"


class TestEfficiencyReportJson:
    def test_json_has_cases_and_aggregates(self) -> None:
        import json

        payload = format_efficiency_report_json(_report())
        parsed = json.loads(payload)
        assert len(parsed["cases"]) == 2
        assert parsed["aggregates"]["insufficient_cases"] == 1
        assert parsed["aggregates"]["all_sufficient"] is False

    def test_json_has_no_claim(self) -> None:
        payload = format_efficiency_report_json(_report())
        assert not _CLAIM.search(payload), f"claim-like token in JSON:\n{payload}"

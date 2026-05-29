"""Tests for benchmark markdown report."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.evaluation.benchmark_suite import (
    BenchmarkSuite,
    format_benchmark_report_markdown,
)


class TestBenchmarkMarkdownReport:
    """Markdown report formatting tests."""

    def test_report_contains_summary(self) -> None:
        suite = BenchmarkSuite()
        result = suite.run(case_ids=["completeness/minimal"])
        report = format_benchmark_report_markdown(result)
        assert "# OpenContext Benchmark Report" in report
        assert "Summary" in report
        assert "1/1 passed" in report

    def test_report_contains_per_case_results(self) -> None:
        suite = BenchmarkSuite()
        result = suite.run(case_ids=["completeness/minimal", "safety/clean_context"])
        report = format_benchmark_report_markdown(result)
        assert "completeness/minimal" in report
        assert "safety/clean_context" in report
        assert "✅" in report or "❌" in report

    def test_report_includes_dimension_breakdown(self) -> None:
        suite = BenchmarkSuite()
        result = suite.run(case_ids=["completeness/minimal"])
        report = format_benchmark_report_markdown(result)
        assert "Completeness" in report
        assert "Relevance" in report

    def test_report_writes_to_file(self, tmp_path: Path) -> None:
        suite = BenchmarkSuite()
        result = suite.run(case_ids=["completeness/minimal"])
        output = tmp_path / "report.md"
        report = format_benchmark_report_markdown(result, output_path=output)
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert content == report

    def test_report_has_recommendations_section(self) -> None:
        suite = BenchmarkSuite()
        result = suite.run_all()  # Run all to get recommendations
        report = format_benchmark_report_markdown(result)
        assert "Recommendations" in report

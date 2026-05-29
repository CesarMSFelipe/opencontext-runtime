"""Tests for context benchmark suite module."""

from __future__ import annotations

from opencontext_core.evaluation.benchmark_suite import (
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkSuite,
    BenchmarkSuiteResult,
    ContextScore,
    ContextScorer,
    QualityDimension,
    compare_results,
    format_benchmark_result,
    format_benchmark_result_json,
)


class TestContextScore:
    """ContextScore model tests."""

    def test_defaults(self) -> None:
        score = ContextScore(overall=85.0, dimensions={QualityDimension.COMPLETENESS: 90.0})
        assert score.overall == 85.0
        assert score.dimensions[QualityDimension.COMPLETENESS] == 90.0
        assert score.recommendations == []

    def test_to_dict(self) -> None:
        score = ContextScore(
            overall=85.0,
            dimensions={
                QualityDimension.COMPLETENESS: 90.0,
                QualityDimension.RELEVANCE: 80.0,
            },
        )
        d = score.to_dict()
        assert d["overall"] == 85.0
        assert d["dimensions"]["completeness"] == 90.0
        assert "recommendations" in d


class TestContextScorer:
    """ContextScorer algorithm tests."""

    def test_perfect_score(self) -> None:
        scorer = ContextScorer()
        score = scorer.score_custom(
            sources=["a.py", "b.py"],
            tokens=500,
            baseline_tokens=2500,
            has_pii=False,
            age_hours=0.5,
        )
        assert score.overall > 90  # Should be very high

    def test_stale_context(self) -> None:
        scorer = ContextScorer()
        score = scorer.score_custom(
            sources=["a.py"],
            tokens=500,
            baseline_tokens=500,
            age_hours=72,  # 3 days old
        )
        assert score.dimensions[QualityDimension.FRESHNESS] < 60

    def test_no_sources(self) -> None:
        scorer = ContextScorer()
        score = scorer.score_custom(
            sources=[],
            tokens=0,
            baseline_tokens=0,
            age_hours=0,
        )
        assert score.overall < 60  # Low score for empty context

    def test_pii_penalty(self) -> None:
        scorer = ContextScorer()
        clean = scorer.score_custom(
            sources=["a.py"],
            tokens=500,
            baseline_tokens=1000,
            has_pii=False,
            age_hours=0,
        )
        dirty = scorer.score_custom(
            sources=["a.py"],
            tokens=500,
            baseline_tokens=1000,
            has_pii=True,
            age_hours=0,
        )
        assert dirty.dimensions[QualityDimension.SAFETY] < clean.dimensions[QualityDimension.SAFETY]

    def test_freshness_decay(self) -> None:
        scorer = ContextScorer()
        fresh = scorer._freshness_from_age(0.5)
        assert fresh == 100.0

        day_old = scorer._freshness_from_age(24)
        assert day_old == 50.0

        week_old = scorer._freshness_from_age(168)
        assert week_old == 20.0

        month_old = scorer._freshness_from_age(720)
        assert month_old < 20


class TestBenchmarkSuite:
    """Benchmark suite runner tests."""

    def test_list_all_cases(self) -> None:
        suite = BenchmarkSuite()
        cases = suite.list_cases()
        assert len(cases) >= 6

    def test_list_by_category(self) -> None:
        suite = BenchmarkSuite()
        completeness = suite.list_cases(category="completeness")
        assert all(c.category == "completeness" for c in completeness)

    def test_run_all(self) -> None:
        suite = BenchmarkSuite()
        result = suite.run_all()
        assert result.total_cases >= 6
        assert isinstance(result.passed, int)
        assert 0 <= result.average_score <= 100
        assert len(result.results) == result.total_cases

    def test_load_bearing_all_pass(self) -> None:
        """Load-bearing test: all built-in cases must pass consistently."""
        suite = BenchmarkSuite()
        result = suite.run_all()
        assert result.passed == len(suite.list_cases()), (
            f"Expected all {len(suite.list_cases())} cases to pass, "
            f"got {result.passed}/{result.total_cases}"
        )

    def test_run_invalid_id_raises(self) -> None:
        """Running with an unknown case ID should raise ValueError."""
        suite = BenchmarkSuite()
        import pytest

        with pytest.raises(ValueError, match="No matching cases"):
            suite.run(case_ids=["nonexistent/case"])

    def test_run_specific(self) -> None:
        suite = BenchmarkSuite()
        result = suite.run(case_ids=["completeness/minimal", "safety/clean_context"])
        assert result.total_cases == 2

    def test_result_details(self) -> None:
        suite = BenchmarkSuite()
        result = suite.run(case_ids=["completeness/minimal"])
        r = result.results[0]
        assert r.case_id == "completeness/minimal"
        assert r.score.overall >= 0
        assert r.duration_ms >= 0


class TestBenchmarkResultFormatting:
    """Output formatting tests."""

    def test_human_readable(self) -> None:
        suite = BenchmarkSuite()
        result = suite.run(case_ids=["completeness/minimal"])
        output = format_benchmark_result(result)
        assert "Benchmark Results" in output
        assert "completeness/minimal" in output

    def test_json(self) -> None:
        suite = BenchmarkSuite()
        result = suite.run(case_ids=["completeness/minimal"])
        import json

        parsed = json.loads(format_benchmark_result_json(result))
        assert "summary" in parsed
        assert parsed["summary"]["total"] == 1

    def test_compare(self) -> None:
        suite = BenchmarkSuite()
        before = suite.run(case_ids=["completeness/minimal"])
        after = suite.run(case_ids=["completeness/minimal", "safety/clean_context"])
        diff = compare_results(before, after)
        assert "Benchmark Comparison" in diff
        assert "completeness/minimal" in diff


class TestBenchmarkDataClasses:
    """Benchmark dataclass tests."""

    def test_benchmark_case(self) -> None:
        case = BenchmarkCase(
            id="test/case",
            name="Test",
            description="A test case",
            category="completeness",
            setup={},
            expected_min_score=80,
        )
        assert case.id == "test/case"
        assert case.expected_min_score == 80

    def test_benchmark_case_result(self) -> None:
        score = ContextScore(overall=95.0, dimensions={})
        result = BenchmarkCaseResult(
            case_id="test/case",
            passed=True,
            score=score,
            details="All good",
            duration_ms=10.5,
        )
        assert result.passed
        assert result.score.overall == 95.0

    def test_benchmark_suite_result(self) -> None:
        result = BenchmarkSuiteResult(
            timestamp="t",
            total_cases=5,
            passed=4,
            failed=1,
            average_score=80.0,
            results=[],
        )
        assert result.passed == 4
        assert result.failed == 1
        assert result.average_score == 80.0

    def test_suite_result_to_dict(self) -> None:
        result = BenchmarkSuiteResult(
            timestamp="2025-01-01T00:00:00",
            total_cases=2,
            passed=2,
            failed=0,
            average_score=95.0,
            results=[],
        )
        d = result.to_dict()
        assert d["summary"]["total"] == 2
        assert d["summary"]["passed"] == 2

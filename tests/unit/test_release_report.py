"""Unit tests for scripts/release_report.py (RELEASE_CONTRACT release report).

Pure-logic coverage: pytest summary-line parsing and GAP-id extraction from an
acceptance log. No subprocesses, no filesystem beyond tmp_path.
"""

from __future__ import annotations

from scripts.release_report import collect_gap_ids, parse_pytest_summary


class TestParsePytestSummary:
    def test_parses_all_passed(self) -> None:
        log = "..........\n42 passed in 208.51s (0:03:28)\n"
        assert parse_pytest_summary(log) == {"passed": 42, "failed": 0, "xfailed": 0}

    def test_parses_mixed_outcomes(self) -> None:
        log = "3 failed, 36 passed, 2 xfailed, 1 xpassed in 100.00s\n"
        assert parse_pytest_summary(log) == {"passed": 36, "failed": 3, "xfailed": 2}

    def test_parses_bracketed_summary_line(self) -> None:
        log = "====== 5 passed, 1 xfailed in 3.21s ======\n"
        assert parse_pytest_summary(log) == {"passed": 5, "failed": 0, "xfailed": 1}

    def test_ignores_warning_counts(self) -> None:
        log = "12 passed, 3 warnings in 9.99s\n"
        assert parse_pytest_summary(log) == {"passed": 12, "failed": 0, "xfailed": 0}

    def test_uses_last_summary_line(self) -> None:
        log = "1 failed in 0.10s\n(retry)\n7 passed in 1.00s\n"
        assert parse_pytest_summary(log) == {"passed": 7, "failed": 0, "xfailed": 0}

    def test_errors_count_as_failures(self) -> None:
        log = "2 passed, 1 error in 0.50s\n"
        assert parse_pytest_summary(log) == {"passed": 2, "failed": 1, "xfailed": 0}

    def test_no_summary_line_returns_none(self) -> None:
        assert parse_pytest_summary("...... [100%]\n") is None


class TestCollectGapIds:
    def test_extracts_gap_ids_from_xfail_lines(self) -> None:
        log = (
            "XFAIL tests/acceptance/test_x.py::test_a - GAP-101: pack metrics missing\n"
            "XFAIL tests/acceptance/test_y.py::test_b - GAP-207: no tui screen\n"
            "PASSED tests/acceptance/test_z.py::test_c\n"
        )
        assert collect_gap_ids(log) == ["GAP-101", "GAP-207"]

    def test_deduplicates_and_sorts(self) -> None:
        log = "XFAIL a - GAP-9: x\nXFAIL b - GAP-9: x\nXFAIL c - GAP-10: y\n"
        assert collect_gap_ids(log) == ["GAP-10", "GAP-9"]

    def test_ignores_gap_ids_outside_xfail_lines(self) -> None:
        log = "PASSED test_gap_doc.py::test_mentions - closes GAP-3\n"
        assert collect_gap_ids(log) == []

    def test_empty_log_yields_no_gaps(self) -> None:
        assert collect_gap_ids("") == []

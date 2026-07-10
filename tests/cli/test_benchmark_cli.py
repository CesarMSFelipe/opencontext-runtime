"""CLI tests for the honest efficiency benchmark command.

The fake benchmark CLI (fabricated cases, "OpenContext Benchmark Results" header)
was rewired to the real CON-vs-SIN efficiency benchmark. These tests assert the
honest surface: list shows real contextbench cases with difficulty/target, and a run
emits per-case CON vs SIN cost with NO "%"/claim string. Runs are scoped to a single
simple case with ``--no-refresh`` to keep them fast (the project is already indexed
in the test environment).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
_CLAIM = re.compile(r"%|reduction_pct|\bbadge\b|fewer tokens", re.IGNORECASE)


def _run_cli(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    """Run the opencontext CLI as a subprocess from the project root."""
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
        timeout=timeout,
    )


class TestBenchmarkCliSurface:
    def test_benchmark_help(self) -> None:
        result = _run_cli("benchmark", "--help")
        assert result.returncode == 0
        assert "list" in result.stdout and "run" in result.stdout

    def test_benchmark_list_shows_real_cases(self) -> None:
        result = _run_cli("benchmark", "list")
        assert result.returncode == 0
        # Real efficiency cases (converted from BUILTIN_SCENARIOS), not fake categories.
        assert "Efficiency Benchmark Cases" in result.stdout
        assert "simple/bridge-count-method" in result.stdout
        # The fabricated cases must be gone.
        assert "completeness/minimal" not in result.stdout

    def test_benchmark_list_category_filters_by_difficulty(self) -> None:
        result = _run_cli("benchmark", "list", "--category", "hard")
        assert result.returncode == 0
        assert "hard/workflow-async-tracing" in result.stdout
        assert "simple/bridge-count-method" not in result.stdout

    def test_benchmark_list_empty_category(self) -> None:
        result = _run_cli("benchmark", "list", "--category", "nonexistent")
        assert result.returncode == 0
        assert "No benchmark cases yet" in result.stdout


class TestBenchmarkCliRun:
    @pytest.mark.slow
    def test_run_single_case_json_reports_con_and_sin(self) -> None:
        result = _run_cli(
            "benchmark",
            "run",
            "--case",
            "simple/bridge-count-method",
            "--format",
            "json",
            "--no-refresh",
        )
        # Exit code reflects quality parity; on a real index this case should be
        # sufficient, but we assert the SHAPE regardless of pass/fail.
        data = json.loads(result.stdout)
        assert "cases" in data and len(data["cases"]) == 1
        case = data["cases"][0]
        assert case["case_id"] == "simple/bridge-count-method"
        assert case["con"]["tool_calls"] == 1  # honest single context call
        assert "tokens" in case["con"] and "tokens" in case["sin"]
        assert "token_delta" in case
        # No marketing claim anywhere in the JSON.
        assert not _CLAIM.search(result.stdout)

    def test_run_text_has_no_claim_string(self) -> None:
        result = _run_cli(
            "benchmark",
            "run",
            "--case",
            "simple/bridge-count-method",
            "--no-refresh",
        )
        assert "efficiency benchmark" in result.stdout.lower()
        assert not _CLAIM.search(result.stdout), result.stdout

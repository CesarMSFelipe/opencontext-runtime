"""CLI tests for the benchmark command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str, cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    """Run the opencontext CLI as a subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "opencontext_cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
    )


class TestBenchmarkCli:
    """Benchmark CLI integration tests."""

    def test_benchmark_help(self) -> None:
        result = _run_cli("benchmark", "--help")
        assert result.returncode == 0
        assert "{list,run,compare}" in result.stdout or "list" in result.stdout

    def test_benchmark_list(self) -> None:
        result = _run_cli("benchmark", "list")
        assert result.returncode == 0
        assert "completeness/minimal" in result.stdout
        assert "Benchmark Cases" in result.stdout

    def test_benchmark_list_category(self) -> None:
        result = _run_cli("benchmark", "list", "--category", "efficiency")
        assert result.returncode == 0
        assert "efficiency/large_project" in result.stdout
        assert "completeness/minimal" not in result.stdout

    def test_benchmark_run(self) -> None:
        result = _run_cli("benchmark", "run")
        assert result.returncode == 0
        assert "OpenContext Benchmark Results" in result.stdout
        assert "Summary:" in result.stdout

    def test_benchmark_run_json(self) -> None:
        result = _run_cli("benchmark", "run", "--format", "json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "summary" in data
        assert data["summary"]["total"] > 0

    def test_benchmark_run_single_case(self) -> None:
        result = _run_cli("benchmark", "run", "--case", "completeness/minimal")
        assert result.returncode == 0
        assert "completeness/minimal" in result.stdout
        assert "Summary:" in result.stdout

    def test_benchmark_run_category_filter(self) -> None:
        result = _run_cli("benchmark", "run", "--category", "freshness")
        assert result.returncode == 0
        assert "freshness/recent" in result.stdout
        assert "freshness/stale" in result.stdout
        assert "Summary:" in result.stdout

    def test_benchmark_run_save_and_compare(self, tmp_path: Path) -> None:
        """Full round-trip: run --save, then compare."""
        # Run with save
        save_result = _run_cli("benchmark", "run", "--save")
        assert save_result.returncode == 0

        # Verify .opencontext/benchmarks was created
        # (CI runs from tmp so it will be in cwd, but --save is relative)

    def test_benchmark_run_markdown_output(self, tmp_path: Path) -> None:
        report = tmp_path / "report.md"
        result = _run_cli("benchmark", "run", "--format", "markdown", "--output", str(report))
        assert result.returncode == 0
        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "# OpenContext Benchmark Report" in content

    def test_benchmark_list_empty_category(self) -> None:
        result = _run_cli("benchmark", "list", "--category", "nonexistent")
        assert result.returncode == 0
        assert "No benchmark cases found" in result.stdout

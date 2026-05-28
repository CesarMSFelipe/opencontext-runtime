"""Tests for benchmark persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.evaluation.benchmark_suite import (
    BenchmarkSuite,
    load_last_result,
    save_result,
)


class TestBenchmarkPersistence:
    """Benchmark save/load round-trip tests."""

    def test_save_result_creates_file(self, tmp_path: str | Path) -> None:
        suite = BenchmarkSuite()
        result = suite.run_all()
        path = save_result(result, directory=tmp_path)
        assert path.exists()
        assert path.suffix == ".json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "summary" in data
        assert data["summary"]["total"] == result.total_cases

    def test_save_result_creates_directory(self, tmp_path: str | Path) -> None:
        nested = Path(tmp_path) / "benchmarks" / "runs"
        suite = BenchmarkSuite()
        result = suite.run(case_ids=["completeness/minimal"])
        path = save_result(result, directory=nested)
        assert path.exists()
        assert nested.exists()

    def test_load_last_result_returns_result(self, tmp_path: str | Path) -> None:
        suite = BenchmarkSuite()
        result = suite.run_all()
        save_result(result, directory=tmp_path)
        loaded = load_last_result(directory=tmp_path)
        assert loaded is not None
        assert loaded.total_cases == result.total_cases
        assert loaded.passed == result.passed
        assert abs(loaded.average_score - result.average_score) < 0.1

    def test_load_last_result_none_when_empty(self, tmp_path: str | Path) -> None:
        loaded = load_last_result(directory=tmp_path)
        assert loaded is None

    def test_load_last_result_picks_latest(self, tmp_path: str | Path) -> None:
        suite = BenchmarkSuite()
        r1 = suite.run(case_ids=["completeness/minimal"])
        r2 = suite.run(case_ids=["completeness/minimal", "safety/clean_context"])

        save_result(r1, directory=tmp_path)
        import time

        time.sleep(0.01)  # Ensure different timestamps
        save_result(r2, directory=tmp_path)

        loaded = load_last_result(directory=tmp_path)
        assert loaded is not None
        assert loaded.total_cases == 2  # The latest has 2 cases

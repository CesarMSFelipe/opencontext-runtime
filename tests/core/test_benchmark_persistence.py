"""Round-trip persistence tests for the honest efficiency report.

The fake ``BenchmarkSuite`` persistence (typed to fabricated results) was EXCISED.
These tests now save/load real :class:`EfficiencyReport` objects.
"""

from __future__ import annotations

import time
from pathlib import Path

from opencontext_core.evaluation.efficiency import (
    load_last_efficiency_result,
    save_efficiency_result,
)
from opencontext_core.evaluation.models import (
    CostTriple,
    EfficiencyCaseResult,
    EfficiencyReport,
)


def _report(case_id: str, con_tokens: int, sin_tokens: int) -> EfficiencyReport:
    return EfficiencyReport(
        cases=[
            EfficiencyCaseResult(
                case_id=case_id,
                difficulty="simple",
                con=CostTriple(tokens=con_tokens, tool_calls=1, latency_ms=5.0),
                sin=CostTriple(tokens=sin_tokens, tool_calls=7, latency_ms=30.0),
                ceiling_tokens=99999,
                con_sufficient=True,
                source_coverage=1.0,
                forbidden_hits=[],
                reasons=["quality parity met"],
            )
        ]
    )


class TestEfficiencyPersistence:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        path = save_efficiency_result(_report("c1", 300, 1200), directory=tmp_path)
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_creates_nested_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "benchmarks" / "runs"
        path = save_efficiency_result(_report("c1", 300, 1200), directory=nested)
        assert path.exists()
        assert nested.exists()

    def test_round_trip_preserves_cost(self, tmp_path: Path) -> None:
        report = _report("c1", 300, 1200)
        save_efficiency_result(report, directory=tmp_path)
        loaded = load_last_efficiency_result(directory=tmp_path)
        assert loaded is not None
        assert len(loaded.cases) == 1
        case = loaded.cases[0]
        assert case.con.tokens == 300
        assert case.con.tool_calls == 1
        assert case.sin.tokens == 1200
        assert case.token_delta == 900  # derived property reconstructed cleanly
        assert case.con_sufficient is True

    def test_load_none_when_empty(self, tmp_path: Path) -> None:
        assert load_last_efficiency_result(directory=tmp_path) is None

    def test_load_picks_latest(self, tmp_path: Path) -> None:
        save_efficiency_result(_report("first", 300, 1200), directory=tmp_path)
        time.sleep(1.05)  # filenames are second-resolution; ensure a distinct stamp
        save_efficiency_result(_report("second", 100, 900), directory=tmp_path)
        loaded = load_last_efficiency_result(directory=tmp_path)
        assert loaded is not None
        assert loaded.cases[0].case_id == "second"

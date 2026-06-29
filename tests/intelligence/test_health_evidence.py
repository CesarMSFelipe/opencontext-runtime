"""Health evidence collector reads real on-disk signals (B9 / AVH-016).

Each assertion writes the evidence with the production telemetry/runner sinks, so
the collector is exercised against the same artifacts the runtime emits.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.indexing.graph_health import GraphHealthReport
from opencontext_core.runtime_intelligence import events as ri_events
from opencontext_core.runtime_intelligence import telemetry_layout
from opencontext_core.runtime_intelligence.health import RuntimeHealth
from opencontext_core.runtime_intelligence.health_evidence import collect_health_evidence


def _healthy_kg() -> GraphHealthReport:
    return GraphHealthReport(status="healthy", indexed=True, nodes=10)


def test_absent_evidence_yields_empty_kwargs(tmp_path: Path) -> None:
    # A fresh project with no telemetry → no evidence → every optional dimension
    # is reported UNMEASURED rather than fabricated.
    assert collect_health_evidence(tmp_path) == {}
    report = RuntimeHealth().report(
        tmp_path, graph_health=_healthy_kg(), **collect_health_evidence(tmp_path)
    )
    assert "cost_calibration" in report.unmeasured_dimensions
    assert "benchmark_trend" in report.unmeasured_dimensions
    assert "selector_accuracy" in report.unmeasured_dimensions


def test_cost_events_become_cost_error_pcts(tmp_path: Path) -> None:
    telemetry_layout.append_event(
        ri_events.COST_REPORTED, {"run_id": "r1", "estimate_error_pct": 12.5}, tmp_path
    )
    telemetry_layout.append_event(
        ri_events.COST_REPORTED, {"run_id": "r2", "estimate_error_pct": -8.0}, tmp_path
    )
    evidence = collect_health_evidence(tmp_path)
    assert evidence["cost_error_pcts"] == [12.5, -8.0]
    report = RuntimeHealth().report(tmp_path, graph_health=_healthy_kg(), **evidence)
    assert "cost_calibration" in report.dimensions


def test_benchmark_history_becomes_trend(tmp_path: Path) -> None:
    history = [
        {
            "timestamp": "2026-06-29T00:00:00Z",
            "results": [
                {"suite": "oc-flow", "task_id": "t1", "measured": True, "success": True},
                {"suite": "first-run", "task_id": "t2", "measured": True, "success": True},
            ],
        }
    ]
    path = tmp_path / telemetry_layout.TELEMETRY_DIR / telemetry_layout.BENCHMARK_HISTORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history), encoding="utf-8")
    evidence = collect_health_evidence(tmp_path)
    assert evidence["efficiency_all_sufficient"] is True
    report = RuntimeHealth().report(tmp_path, graph_health=_healthy_kg(), **evidence)
    assert report.dimensions["benchmark_trend"] > 0.5


def test_recorded_decisions_drive_selector_accuracy(tmp_path: Path) -> None:
    run_dir = tmp_path / ".opencontext" / "sessions" / "sess-1" / "runs" / "run-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    decisions = {
        "decisions": [
            {"kind": "next_node", "governed_by": None},  # accepted recommendation
            {"kind": "next_node", "governed_by": "state_machine"},  # overridden
        ]
    }
    (run_dir / "decisions.json").write_text(json.dumps(decisions), encoding="utf-8")
    evidence = collect_health_evidence(tmp_path)
    assert "decision_log" in evidence
    report = RuntimeHealth().report(tmp_path, graph_health=_healthy_kg(), **evidence)
    assert "selector_accuracy" in report.dimensions
    assert report.dimensions["selector_accuracy"] == 0.5

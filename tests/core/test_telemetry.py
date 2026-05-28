"""Tests for token savings telemetry."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from opencontext_core.evaluation.telemetry import (
    TelemetryEvent,
    load_telemetry,
    record_event,
    record_from_benchmark,
)


class TestTelemetry:
    def test_record_and_load(self, tmp_path: Path) -> None:
        """Record an event, load it back, verify all fields."""
        ts = time.time()
        event = TelemetryEvent(
            timestamp=ts,
            task="test task",
            naive_tokens=1000,
            optimized_tokens=600,
            reduction_pct=40.0,
            scenario="s1",
        )
        record_event(event, root=tmp_path)

        store = load_telemetry(root=tmp_path)
        assert len(store.events) == 1
        loaded = store.events[0]
        assert loaded.task == "test task"
        assert loaded.naive_tokens == 1000
        assert loaded.optimized_tokens == 600
        assert loaded.reduction_pct == 40.0
        assert loaded.scenario == "s1"

    def test_total_saved_calculation(self, tmp_path: Path) -> None:
        """Two events: verify total_saved is correct."""
        record_event(
            TelemetryEvent(
                timestamp=time.time(),
                task="task a",
                naive_tokens=2000,
                optimized_tokens=1200,
                reduction_pct=40.0,
            ),
            root=tmp_path,
        )
        record_event(
            TelemetryEvent(
                timestamp=time.time(),
                task="task b",
                naive_tokens=1000,
                optimized_tokens=500,
                reduction_pct=50.0,
            ),
            root=tmp_path,
        )

        store = load_telemetry(root=tmp_path)
        assert store.total_naive == 3000
        assert store.total_optimized == 1700
        assert store.total_saved == 1300

    def test_average_reduction(self, tmp_path: Path) -> None:
        """Verify average_reduction calculation."""
        record_event(
            TelemetryEvent(
                timestamp=time.time(),
                task="t1",
                naive_tokens=1000,
                optimized_tokens=600,
                reduction_pct=40.0,
            ),
            root=tmp_path,
        )
        record_event(
            TelemetryEvent(
                timestamp=time.time(),
                task="t2",
                naive_tokens=1000,
                optimized_tokens=400,
                reduction_pct=60.0,
            ),
            root=tmp_path,
        )

        store = load_telemetry(root=tmp_path)
        assert store.average_reduction == pytest.approx(50.0)

    def test_empty_store(self, tmp_path: Path) -> None:
        """Empty store returns zero for all aggregates."""
        store = load_telemetry(root=tmp_path)
        assert store.total_naive == 0
        assert store.total_optimized == 0
        assert store.total_saved == 0
        assert store.average_reduction == 0.0
        assert store.session_count == 0

    def test_record_from_benchmark(self, tmp_path: Path) -> None:
        """Record from a mock ComparativeReport object."""

        class MockScenario:
            task = "benchmark task"
            naive_tokens = 5000
            optimized_tokens = 3000
            reduction_pct = 40.0
            scenario_id = "bench-1"

        class MockReport:
            scenarios = [MockScenario(), MockScenario()]

        record_from_benchmark(MockReport(), root=tmp_path)

        store = load_telemetry(root=tmp_path)
        assert len(store.events) == 2
        assert store.events[0].task == "benchmark task"
        assert store.events[0].naive_tokens == 5000
        assert store.events[0].scenario == "bench-1"
        assert store.total_saved == 4000

"""Tests for metrics collector."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.metrics import MetricsCollector, OperationMetrics


class TestOperationMetrics:
    """Test operation metrics."""

    def test_duration(self) -> None:
        import time

        m = OperationMetrics(operation="test", start_time=time.time())
        time.sleep(0.01)
        m.end_time = time.time()
        assert m.duration_ms >= 10

    def test_total_tokens(self) -> None:
        m = OperationMetrics(operation="test", start_time=0, input_tokens=10, output_tokens=20)
        assert m.total_tokens == 30

    def test_to_dict(self) -> None:
        m = OperationMetrics(
            operation="test", start_time=0, end_time=1, input_tokens=10, output_tokens=20
        )
        d = m.to_dict()
        assert d["operation"] == "test"
        assert d["input_tokens"] == 10
        assert d["output_tokens"] == 20


class TestMetricsCollector:
    """Test metrics collector."""

    def test_start_stop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            MetricsCollector,
            "__init__",
            lambda self, metrics_dir=".opencontext/metrics": (
                setattr(self, "metrics_dir", tmp_path)
                or setattr(self, "_current", {})
                or setattr(self, "_history", [])
            ),
        )
        collector = MetricsCollector(tmp_path)
        op_id = collector.start("test_op")
        assert op_id in collector._current

        metrics = collector.stop(op_id, input_tokens=10, output_tokens=5)
        assert metrics.operation == "test_op"
        assert metrics.input_tokens == 10
        assert metrics.output_tokens == 5
        assert len(collector._history) == 1

    def test_summary_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            MetricsCollector,
            "__init__",
            lambda self, metrics_dir=".opencontext/metrics": (
                setattr(self, "metrics_dir", tmp_path)
                or setattr(self, "_current", {})
                or setattr(self, "_history", [])
            ),
        )
        collector = MetricsCollector(tmp_path)
        summary = collector.get_summary()
        assert summary["total_operations"] == 0

    def test_summary_with_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            MetricsCollector,
            "__init__",
            lambda self, metrics_dir=".opencontext/metrics": (
                setattr(self, "metrics_dir", tmp_path)
                or setattr(self, "_current", {})
                or setattr(self, "_history", [])
            ),
        )
        collector = MetricsCollector(tmp_path)
        op1 = collector.start("op1")
        collector.stop(op1, input_tokens=10, output_tokens=5)
        op2 = collector.start("op2")
        collector.stop(op2, input_tokens=20, output_tokens=10)

        summary = collector.get_summary()
        assert summary["total_operations"] == 2
        assert summary["total_tokens"] == 45

    def test_clear(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            MetricsCollector,
            "__init__",
            lambda self, metrics_dir=".opencontext/metrics": (
                setattr(self, "metrics_dir", tmp_path)
                or setattr(self, "_current", {})
                or setattr(self, "_history", [])
            ),
        )
        collector = MetricsCollector(tmp_path)
        op = collector.start("test")
        collector.stop(op)
        collector.clear()
        assert len(collector._history) == 0

"""Tests for context observability module."""

from __future__ import annotations

from opencontext_core.context.observability import (
    format_duration,
    format_tokens,
    format_cost,
    MetricPoint,
    estimate_cost,
)


class TestFormatters:
    """Formatting helper tests."""

    def test_format_duration(self) -> None:
        assert format_duration(100) == "100ms"
        assert format_duration(1500) == "1.5s"
        assert format_duration(65000) == "1.1m"
        assert format_duration(0.5) == "500µs"

    def test_format_tokens(self) -> None:
        assert format_tokens(500) == "500"
        assert format_tokens(1500) == "1.5K"
        assert format_tokens(1500000) == "1.5M"

    def test_format_cost(self) -> None:
        assert format_cost(0.0) == "$0.0000"
        assert format_cost(0.05) == "$0.050"
        assert format_cost(1.23) == "$1.23"
        assert format_cost(5.0) == "$5.00"


class TestMetricPoint:
    """MetricPoint data model tests."""

    def test_defaults(self) -> None:
        p = MetricPoint(name="test.metric", value=42.0)
        assert p.name == "test.metric"
        assert p.value == 42.0
        assert p.timestamp == ""
        assert p.attributes == {}
        assert p.unit == ""

    def test_full(self) -> None:
        p = MetricPoint("test.m", 1.0, "2025-01-01", {"key": "val"}, "ms")
        assert p.unit == "ms"
        assert p.attributes["key"] == "val"


class TestCostEstimation:
    """Cost estimation tests."""

    def test_known_provider(self) -> None:
        cost = estimate_cost("openai", "gpt-4", 1000)
        assert cost == 0.03  # $0.03 per 1K tokens

    def test_unknown_provider(self) -> None:
        cost = estimate_cost("unknown", "model", 1000)
        assert cost == 0.002  # default rate

    def test_mock_provider(self) -> None:
        cost = estimate_cost("mock", "mock-llm", 10000)
        assert cost == 0.0

    def test_zero_tokens(self) -> None:
        cost = estimate_cost("openai", "gpt-4", 0)
        assert cost == 0.0

    def test_wildcard_model(self) -> None:
        cost = estimate_cost("openai", "unknown-model", 1000)
        assert cost == 0.003  # openai wildcard rate

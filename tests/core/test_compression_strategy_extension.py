"""Tests for CompressionStrategy COMPACT and DEEP extensions."""

from opencontext_core.models.context import CompressionStrategy


def test_compression_strategy_compact_exists():
    assert CompressionStrategy.COMPACT == "compact"


def test_compression_strategy_deep_exists():
    assert CompressionStrategy.DEEP == "deep"

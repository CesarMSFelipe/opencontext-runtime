"""Tests for D2 pure benchmark functions and fixture loading."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from opencontext_core.memory.benchmark import (
    MemoryBenchmarkQuestion,
    MemoryBenchmarkResult,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


class TestRecallAtK:
    def test_perfect_retrieval_returns_1_0(self) -> None:
        results = ["a", "b", "c", "d", "e"]
        relevant = ["a", "b", "c", "d", "e"]
        assert recall_at_k(results, relevant, k=5) == 1.0

    def test_no_hits_returns_0(self) -> None:
        assert recall_at_k(["x", "y"], ["a", "b"], k=2) == 0.0

    def test_partial_recall(self) -> None:
        results = ["a", "x", "b", "y", "z"]
        relevant = ["a", "b", "c", "d"]
        # 2 hits / 4 relevant = 0.5
        assert recall_at_k(results, relevant, k=5) == pytest.approx(0.5)

    def test_empty_relevant_returns_0(self) -> None:
        assert recall_at_k(["a", "b"], [], k=5) == 0.0

    def test_k_limits_window(self) -> None:
        results = ["x", "a", "b"]  # a and b are relevant but only first k=1 counts
        relevant = ["a", "b"]
        assert recall_at_k(results, relevant, k=1) == 0.0


class TestPrecisionAtK:
    def test_all_relevant(self) -> None:
        assert precision_at_k(["a", "b"], ["a", "b"], k=2) == 1.0

    def test_none_relevant(self) -> None:
        assert precision_at_k(["x", "y"], ["a", "b"], k=2) == 0.0

    def test_half_relevant(self) -> None:
        assert precision_at_k(["a", "x"], ["a", "b"], k=2) == pytest.approx(0.5)

    def test_k_zero_returns_0(self) -> None:
        assert precision_at_k(["a"], ["a"], k=0) == 0.0


class TestReciprocalRank:
    def test_first_hit_at_position_1(self) -> None:
        assert reciprocal_rank(["a", "b", "c"], ["a"]) == pytest.approx(1.0)

    def test_first_hit_at_position_2(self) -> None:
        # 0-based index 1 → 1-based position 2 → RR = 0.5
        assert reciprocal_rank(["x", "a", "b"], ["a"]) == pytest.approx(0.5)

    def test_first_hit_at_position_3(self) -> None:
        assert reciprocal_rank(["x", "y", "a"], ["a"]) == pytest.approx(1 / 3)

    def test_no_hit_returns_0(self) -> None:
        assert reciprocal_rank(["x", "y", "z"], ["a"]) == 0.0

    def test_empty_results_returns_0(self) -> None:
        assert reciprocal_rank([], ["a"]) == 0.0


class TestBenchmarkFixture:
    def test_bundled_fixture_loadable(self) -> None:
        fixture_path = (
            Path(__file__).parent.parent.parent.parent
            / "tests"
            / "fixtures"
            / "memory"
            / "coding-agent-life-v1.json"
        )
        assert fixture_path.exists(), f"Fixture not found at {fixture_path}"
        data = json.loads(fixture_path.read_text())
        assert isinstance(data, list)
        assert len(data) >= 1
        for entry in data:
            assert "query" in entry
            assert "relevant" in entry
            assert len(entry["relevant"]) > 0

    def test_fixture_has_minimum_10_questions(self) -> None:
        fixture_path = (
            Path(__file__).parent.parent.parent.parent
            / "tests"
            / "fixtures"
            / "memory"
            / "coding-agent-life-v1.json"
        )
        data = json.loads(fixture_path.read_text())
        assert len(data) >= 10

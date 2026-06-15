"""Tests for MutationRunner and MutationResult."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from opencontext_core.mutation.models import MutationResult
from opencontext_core.mutation.runner import MutationRunner


class TestMutationResult:
    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(MutationResult)

    def test_defaults_are_correct(self) -> None:
        result = MutationResult(score=0.0, killed=0, survivors=0, available=False, framework="none")
        assert result.score == 0.0
        assert result.killed == 0
        assert result.survivors == 0
        assert result.available is False
        assert result.framework == "none"
        assert result.error is None

    def test_score_range(self) -> None:
        """Score must stay within 0.0-100.0."""
        result = MutationResult(
            score=85.0, killed=17, survivors=3, available=True, framework="some-tool"
        )
        assert 0.0 <= result.score <= 100.0

    def test_available_false_when_framework_none(self) -> None:
        result = MutationResult(score=0.0, killed=0, survivors=0, available=False, framework="none")
        assert result.available is False


class TestMutationRunnerNoFramework:
    def test_no_framework_returns_unavailable(self, tmp_path: Path) -> None:
        """When no framework is installed, runner returns available=False."""
        runner = MutationRunner()
        # tmp_path has no Cargo.toml, no vendor/bin, and test env likely has no mutmut/cosmic-ray
        result = runner.run(tmp_path)
        # The framework may or may not be installed in CI, so we check the contract
        if not result.available:
            assert result.score == 0.0
            assert result.killed == 0
            assert result.survivors == 0
            assert result.error is not None
            # Error message must not expose technology names
            tech_names = ["mutmut", "cosmic-ray", "infection", "cargo-mutants", "pytest-mutagen"]
            for name in tech_names:
                assert name not in result.error, (
                    f"Technology name '{name}' found in error message: {result.error}"
                )
        else:
            # If a framework is found, score must still be in range
            assert 0.0 <= result.score <= 100.0

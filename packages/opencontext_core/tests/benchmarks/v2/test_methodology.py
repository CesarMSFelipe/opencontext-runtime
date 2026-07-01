"""REQ-bench-v1-002: methodology versioning + regression blocks."""

from __future__ import annotations

import pytest

from opencontext_core.benchmarks.v2.methodology import (
    current_methodology_version,
    bump_methodology_version,
    regression_check,
    MethodologyRegression,
    METHODOLOGY_VERSION_FORMAT,
)


def test_REQ_bench_v1_002_version_stamped() -> None:
    v = current_methodology_version()
    assert METHODOLOGY_VERSION_FORMAT.match(v) is not None


def test_REQ_bench_v1_002_regression_blocks() -> None:
    with pytest.raises(MethodologyRegression):
        regression_check(baseline="2026.06.01", current="2025.12.31")


def test_no_regression_when_monotonic() -> None:
    # Same or newer version must not raise.
    regression_check(baseline="2026.06.01", current=bump_methodology_version("2026.06.01"))
"""CI wiring for the benchmark gates + publish-token anti-regression (REL-10/REL-01)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BENCHMARK_YML = REPO / ".github" / "workflows" / "benchmark.yml"
PUBLISH_YML = REPO / ".github" / "workflows" / "publish.yml"


@pytest.fixture(scope="module")
def benchmark_text() -> str:
    assert BENCHMARK_YML.is_file(), "benchmark.yml workflow is missing"
    return BENCHMARK_YML.read_text(encoding="utf-8")


def test_pr_smoke_job_runs_the_smoke_subset(benchmark_text: str) -> None:
    assert "pull_request:" in benchmark_text
    assert "benchmark suite run --smoke" in benchmark_text


def test_nightly_runs_full_suite_and_release_gates(benchmark_text: str) -> None:
    assert "schedule:" in benchmark_text and "cron:" in benchmark_text
    assert "benchmark suite run" in benchmark_text
    assert "release acceptance" in benchmark_text
    assert "release gate" in benchmark_text


def test_nightly_includes_the_layering_guard(benchmark_text: str) -> None:
    assert "tests/architecture" in benchmark_text


def test_publish_uses_pypi_token_not_oidc() -> None:
    """REL-01 / recurring break: publish.yml must keep the PyPI API token, never OIDC."""
    assert PUBLISH_YML.is_file(), "publish.yml is missing"
    text = PUBLISH_YML.read_text(encoding="utf-8")
    assert "secrets.PYPI_API_TOKEN" in text
    assert "id-token: write" not in text  # no OIDC trusted publishing

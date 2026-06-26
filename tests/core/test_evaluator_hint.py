"""T3: evaluator coverage-failure hint for non-OC projects.

When a ContextBenchEvaluator runs on a root that is NOT the OC repo,
a coverage-below-threshold failure reason must include a --root hint.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from opencontext_core.evaluation.evaluator import ContextBenchEvaluator
from opencontext_core.evaluation.models import ContextBenchCase


def _make_evaluator(root: Path) -> ContextBenchEvaluator:
    """Build an evaluator backed by a minimal mock runtime."""
    runtime = MagicMock()
    # prepare_context returns a result with no included sources and few tokens.
    prepared = MagicMock()
    prepared.included_sources = []
    prepared.token_usage = {"final_context_pack": 100}
    runtime.prepare_context.return_value = prepared
    runtime.manifest.return_value = MagicMock(total_tokens=10000)
    evaluator = ContextBenchEvaluator(runtime, root=root, max_tokens=6000, min_token_reduction=0.0)
    return evaluator


def test_coverage_hint_present_for_non_oc_project(tmp_path: Path) -> None:
    """Non-OC root: coverage failure reason must mention --root."""
    evaluator = _make_evaluator(tmp_path)
    case = ContextBenchCase(
        id="c1",
        query="test",
        expected_sources=["some/module.py"],
        min_source_coverage=1.0,
    )
    result = evaluator.evaluate_case(case)
    assert not result.passed
    full_reason = " ".join(result.reasons)
    assert "--root" in full_reason, f"Expected '--root' in reasons: {result.reasons}"


def test_efficiency_hint_present_for_non_oc_project(tmp_path: Path) -> None:
    evaluator = _make_evaluator(tmp_path)
    case = ContextBenchCase(
        id="c3",
        query="test",
        expected_sources=["some/module.py"],
        min_source_coverage=1.0,
    )
    result = evaluator.evaluate_efficiency_case(case)
    full_reason = " ".join(result.reasons)
    assert "--suite your-suite.yaml" in full_reason


def test_coverage_hint_absent_for_oc_project() -> None:
    """OC repo root: coverage failure should NOT include the suite-mismatch hint."""
    import os

    # Use the actual project root (which has packages/opencontext_core)
    oc_root = Path(os.environ.get("OC_PROJECT_ROOT", Path(__file__).parents[2]))
    if not (oc_root / "packages" / "opencontext_core").exists():
        pytest.skip("Test must run from the OC project root")

    runtime = MagicMock()
    prepared = MagicMock()
    prepared.included_sources = []
    prepared.token_usage = {"final_context_pack": 100}
    runtime.prepare_context.return_value = prepared
    runtime.manifest.return_value = MagicMock(total_tokens=10000)
    evaluator = ContextBenchEvaluator(
        runtime, root=oc_root, max_tokens=6000, min_token_reduction=0.0
    )
    case = ContextBenchCase(
        id="c2",
        query="test",
        expected_sources=["some/module.py"],
        min_source_coverage=1.0,
    )
    result = evaluator.evaluate_case(case)
    assert not result.passed
    full_reason = " ".join(result.reasons)
    assert "--root" not in full_reason, f"Hint should be absent for OC root, got: {result.reasons}"

"""Fixtures for the Runtime Intelligence test suite (PR-011)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from opencontext_core.models.context import TokenBudget
from opencontext_core.models.intelligence import BenchmarkResult
from opencontext_core.models.trace import RuntimeTrace


@pytest.fixture
def make_trace() -> Callable[..., RuntimeTrace]:
    """Return a builder for a minimal, valid RuntimeTrace."""

    def _build(
        *,
        run_id: str = "run_test",
        timings_ms: dict[str, float] | None = None,
        input_tokens: int = 5000,
        output_tokens: int = 1200,
    ) -> RuntimeTrace:
        return RuntimeTrace(
            run_id=run_id,
            workflow_name="oc-flow",
            input="fix the failing test",
            provider="mock",
            model="mock",
            selected_context_items=[],
            discarded_context_items=[],
            token_budget=TokenBudget(
                max_input_tokens=8000,
                reserve_output_tokens=1000,
                available_context_tokens=7000,
                sections={},
            ),
            token_estimates={"input": input_tokens, "output": output_tokens},
            compression_strategy="none",
            prompt_sections=[],
            final_answer="done",
            created_at=datetime.now(tz=UTC),
            timings_ms=timings_ms
            if timings_ms is not None
            else {"context_retrieval": 380.0, "diagnosis": 120.0, "planning": 60.0},
        )

    return _build


@pytest.fixture
def bench_result() -> Callable[..., BenchmarkResult]:
    """Return a builder for a BenchmarkResult (promotion-gate tests)."""

    def _build(
        suite: str,
        *,
        success: bool = True,
        measured: bool = True,
        tokens: int = 1000,
        security_passed: bool = True,
    ) -> BenchmarkResult:
        return BenchmarkResult(
            task_id=f"{suite}-case",
            suite=suite,
            measured=measured,
            success=success,
            tokens=tokens,
            security_passed=security_passed,
        )

    return _build

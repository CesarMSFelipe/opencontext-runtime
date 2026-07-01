"""Tests for runtime.intel.attribution — token-savings attribution."""

from __future__ import annotations

import pytest

from opencontext_core.runtime.intel.attribution import (
    TokenSavings,
    TokenSavingsAttribution,
)


def _run(
    *,
    baseline_tokens: int = 10000,
    kg_signature: int = 0,
    semantic_compression: int = 0,
    cache_hit: int = 0,
    local_inspection: int = 0,
    usefulness_score: float | None = None,
) -> dict:
    return {
        "baseline_tokens": baseline_tokens,
        "kg_signature": kg_signature,
        "semantic_compression": semantic_compression,
        "cache_hit": cache_hit,
        "local_inspection": local_inspection,
        "usefulness_score": usefulness_score,
    }


class TestAttributionDecompose:
    def test_returns_four_axes(self) -> None:
        att = TokenSavingsAttribution()
        run = _run(kg_signature=10, semantic_compression=20, cache_hit=30, local_inspection=40)
        result = att.decompose(run)
        assert isinstance(result, TokenSavings)
        assert result.kg_signature == 10
        assert result.semantic_compression == 20
        assert result.cache_hit == 30
        assert result.local_inspection == 40

    def test_total_equals_sum(self) -> None:
        att = TokenSavingsAttribution()
        run = _run(kg_signature=100, semantic_compression=200, cache_hit=50, local_inspection=25)
        result = att.decompose(run)
        assert result.total == 375

    def test_empty_run_yields_zero_total(self) -> None:
        att = TokenSavingsAttribution()
        result = att.decompose(_run())
        assert result.total == 0

    def test_missing_keys_default_to_zero(self) -> None:
        att = TokenSavingsAttribution()
        result = att.decompose({})
        assert result.kg_signature == 0
        assert result.semantic_compression == 0
        assert result.cache_hit == 0
        assert result.local_inspection == 0
        assert result.total == 0

    def test_negative_values_clamped_to_zero(self) -> None:
        att = TokenSavingsAttribution()
        result = att.decompose(_run(kg_signature=-5, semantic_compression=10))
        assert result.kg_signature == 0
        assert result.semantic_compression == 10

    def test_savings_pct_relative_to_baseline(self) -> None:
        att = TokenSavingsAttribution()
        run = _run(
            baseline_tokens=1000,
            semantic_compression=200,
            cache_hit=100,
            local_inspection=50,
        )
        result = att.decompose(run)
        # 350/1000 = 0.35
        assert result.savings_pct == pytest.approx(0.35)

    def test_savings_pct_zero_baseline_safe(self) -> None:
        att = TokenSavingsAttribution()
        result = att.decompose(_run(baseline_tokens=0, semantic_compression=10))
        assert result.savings_pct == 0.0


class TestAttributionConsumer:
    def test_consumes_usefulness_score(self) -> None:
        att = TokenSavingsAttribution()
        result = att.decompose(_run(semantic_compression=100, usefulness_score=0.9))
        # usefulness_score in [0,1] becomes an "applied" weighted savings
        assert result.applied_score == pytest.approx(0.9)

    def test_applied_score_zero_when_no_usefulness(self) -> None:
        att = TokenSavingsAttribution()
        result = att.decompose(_run(usefulness_score=None))
        assert result.applied_score == 0.0

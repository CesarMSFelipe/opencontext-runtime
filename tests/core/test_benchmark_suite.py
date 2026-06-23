"""Tests for the honest context quality scorer (ContextScorer).

The fabricated ``score_custom`` path (hardcoded ``relevance=100.0``) and the
``BenchmarkSuite`` runner over fabricated ``setup`` dicts were EXCISED. These tests
now assert the HONEST scorer, which derives relevance from a REAL pack's
selected/discarded ratio (``score_from_pack``) and the freshness decay curve. Cost
measurement lives in ``test_efficiency_benchmark.py`` (CON vs SIN).
"""

from __future__ import annotations

from opencontext_core.evaluation.benchmark_suite import (
    ContextScore,
    ContextScorer,
    QualityDimension,
)
from opencontext_core.models.context import ContextItem, ContextPackResult, ContextPriority


def _item(source: str, content: str = "x") -> ContextItem:
    return ContextItem(
        id=source,
        source=source,
        source_type="file",
        content=content,
        priority=ContextPriority.P2,
        tokens=max(1, len(content) // 4),
        score=1.0,
    )


def _pack(included: list[ContextItem], omitted: list[ContextItem], used: int, available: int):
    return ContextPackResult(
        included=included,
        omitted=omitted,
        used_tokens=used,
        available_tokens=available,
        omissions=[],
    )


class TestContextScore:
    """ContextScore model tests."""

    def test_defaults(self) -> None:
        score = ContextScore(overall=85.0, dimensions={QualityDimension.COMPLETENESS: 90.0})
        assert score.overall == 85.0
        assert score.dimensions[QualityDimension.COMPLETENESS] == 90.0
        assert score.recommendations == []

    def test_to_dict(self) -> None:
        score = ContextScore(
            overall=85.0,
            dimensions={
                QualityDimension.COMPLETENESS: 90.0,
                QualityDimension.RELEVANCE: 80.0,
            },
        )
        d = score.to_dict()
        assert d["overall"] == 85.0
        assert d["dimensions"]["completeness"] == 90.0
        assert "recommendations" in d


class TestContextScorerFromPack:
    """Honest scoring from a REAL ContextPackResult (relevance is earned, not faked)."""

    def test_relevance_reflects_real_noise_ratio(self) -> None:
        scorer = ContextScorer()
        # All included, nothing omitted → relevance must be the maximum (100).
        clean = scorer.score_from_pack(
            _pack([_item("a.py"), _item("b.py")], [], used=500, available=2500)
        )
        # Half the candidates omitted → relevance must drop below the clean case.
        noisy = scorer.score_from_pack(
            _pack(
                [_item("a.py")],
                [_item("noise1.py"), _item("noise2.py")],
                used=500,
                available=2500,
            )
        )
        assert clean.dimensions[QualityDimension.RELEVANCE] == 100.0
        assert (
            noisy.dimensions[QualityDimension.RELEVANCE]
            < clean.dimensions[QualityDimension.RELEVANCE]
        )

    def test_token_efficiency_rewards_smaller_packs(self) -> None:
        scorer = ContextScorer()
        lean = scorer.score_from_pack(_pack([_item("a.py")], [], used=200, available=2000))
        heavy = scorer.score_from_pack(_pack([_item("a.py")], [], used=1900, available=2000))
        assert (
            lean.dimensions[QualityDimension.TOKEN_EFFICIENCY]
            > heavy.dimensions[QualityDimension.TOKEN_EFFICIENCY]
        )

    def test_pii_penalises_safety(self) -> None:
        scorer = ContextScorer()
        clean = scorer.score_from_pack(_pack([_item("a.py")], [], 200, 1000), has_pii=False)
        dirty = scorer.score_from_pack(_pack([_item("a.py")], [], 200, 1000), has_pii=True)
        assert dirty.dimensions[QualityDimension.SAFETY] < clean.dimensions[QualityDimension.SAFETY]

    def test_empty_pack_is_low_quality(self) -> None:
        scorer = ContextScorer()
        score = scorer.score_from_pack(_pack([], [], 0, 0))
        # No sources, neutral efficiency → overall should not be a perfect score.
        assert score.overall < 100.0


class TestFreshnessDecay:
    def test_freshness_decay_curve(self) -> None:
        scorer = ContextScorer()
        assert scorer._freshness_from_age(0.5) == 100.0
        assert scorer._freshness_from_age(24) == 50.0
        assert scorer._freshness_from_age(168) == 20.0
        assert scorer._freshness_from_age(720) < 20


class TestFakeScorerRemoved:
    """The fabricated, always-100 scorer must NOT be reachable any more."""

    def test_score_custom_is_gone(self) -> None:
        assert not hasattr(ContextScorer, "score_custom"), (
            "score_custom (hardcoded relevance=100.0) must stay excised"
        )

    def test_no_benchmark_suite_runner(self) -> None:
        import opencontext_core.evaluation.benchmark_suite as bs

        for fake in ("BenchmarkSuite", "BUILTIN_CASES", "BenchmarkSuiteResult"):
            assert not hasattr(bs, fake), f"{fake} must stay excised"

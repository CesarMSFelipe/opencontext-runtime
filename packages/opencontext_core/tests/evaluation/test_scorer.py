"""REQ-eval-fw-001: ScoreCalculator computes precision / recall / F1 / MRR."""

from __future__ import annotations

import pytest

from opencontext_core.evaluation.scorer import EvalScore, ScoreCalculator

# ── EvalScore dataclass ──────────────────────────────────────────────────────


def test_eval_score_dataclass_carries_all_metrics() -> None:
    score = EvalScore(precision=0.8, recall=0.6, f1=0.6857, mrr=0.75)
    assert score.precision == 0.8
    assert score.recall == 0.6
    assert score.f1 == pytest.approx(0.6857, rel=1e-3)
    assert score.mrr == 0.75


def test_eval_score_is_immutable() -> None:
    score = EvalScore(precision=0.5, recall=0.5, f1=0.5, mrr=0.5)
    with pytest.raises((AttributeError, Exception)):
        score.precision = 0.9  # type: ignore[misc]


# ── ScoreCalculator: static helpers ──────────────────────────────────────────


def test_precision_basic() -> None:
    assert ScoreCalculator.precision(true_positives=8, false_positives=2) == 0.8


def test_precision_zero_predictions() -> None:
    # No positive predictions → precision is 0.0 (no NaN/div-by-zero).
    assert ScoreCalculator.precision(true_positives=0, false_positives=0) == 0.0


def test_recall_basic() -> None:
    assert ScoreCalculator.recall(true_positives=6, false_negatives=4) == 0.6


def test_recall_zero_relevant() -> None:
    assert ScoreCalculator.recall(true_positives=0, false_negatives=0) == 0.0


def test_f1_harmonic_mean() -> None:
    p, r = 0.8, 0.5
    expected = 2 * p * r / (p + r)
    assert ScoreCalculator.f1(p, r) == pytest.approx(expected)


def test_f1_zero_precision_or_recall() -> None:
    assert ScoreCalculator.f1(0.0, 0.5) == 0.0
    assert ScoreCalculator.f1(0.5, 0.0) == 0.0
    assert ScoreCalculator.f1(0.0, 0.0) == 0.0


def test_mrr_first_rank_one() -> None:
    # All cases have the first relevant doc at rank 1 → MRR = 1.0
    assert ScoreCalculator.mrr([1, 1, 1]) == 1.0


def test_mrr_mixed_ranks() -> None:
    # Mean of (1/1, 1/2, 1/3)
    expected = (1.0 + 0.5 + 1.0 / 3.0) / 3
    assert ScoreCalculator.mrr([1, 2, 3]) == pytest.approx(expected)


def test_mrr_empty_ranks() -> None:
    assert ScoreCalculator.mrr([]) == 0.0


def test_mrr_skips_zero_ranks() -> None:
    # rank=0 means "no relevant doc found" — reciprocals would divide by zero.
    # Contract: those contribute 0.0 to the mean.
    assert ScoreCalculator.mrr([1, 0, 2]) == pytest.approx((1.0 + 0.0 + 0.5) / 3)


# ── ScoreCalculator.compute ──────────────────────────────────────────────────


def test_compute_retrieval_perfect() -> None:
    y_true = {"a", "b", "c"}
    y_pred = ["a", "b", "c", "d"]
    s = ScoreCalculator().compute(y_true, y_pred)
    assert s.precision == 0.75  # 3 / 4
    assert s.recall == 1.0  # 3 / 3
    assert s.f1 == pytest.approx(2 * 0.75 * 1.0 / (0.75 + 1.0))
    # MRR: first relevant (a) at rank 1 → 1.0
    assert s.mrr == 1.0


def test_compute_retrieval_partial() -> None:
    y_true = {"a", "b", "c"}
    y_pred = ["x", "a", "y", "b"]  # 'c' missing
    s = ScoreCalculator().compute(y_true, y_pred)
    # tp=2, fp=2, fn=1
    assert s.precision == 0.5
    assert s.recall == pytest.approx(2.0 / 3.0)
    # first relevant 'a' at rank 2
    assert s.mrr == 0.5


def test_compute_no_matches_mrr_is_zero() -> None:
    y_true = {"a"}
    y_pred = ["x", "y", "z"]
    s = ScoreCalculator().compute(y_true, y_pred)
    assert s.precision == 0.0
    assert s.recall == 0.0
    assert s.f1 == 0.0
    assert s.mrr == 0.0


def test_compute_accepts_list_y_true() -> None:
    # The signature must accept either set or list for y_true.
    s = ScoreCalculator().compute(["a", "b"], ["a", "c"])
    assert s.precision == 0.5
    assert s.recall == 0.5


def test_compute_with_custom_ranks() -> None:
    # Explicit ranks for MRR; useful when rank is supplied separately
    # from retrieval order (e.g. for ranking-only tasks).
    s = ScoreCalculator().compute({"a"}, ["a"], ranks=[3])
    assert s.precision == 1.0
    assert s.recall == 1.0
    assert s.mrr == pytest.approx(1.0 / 3.0)

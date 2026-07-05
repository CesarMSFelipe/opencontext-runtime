"""REQ-eval-fw-001: ScoreCalculator computes precision / recall / F1 / MRR.

The eval framework needs canonical retrieval-quality metrics so that all
6 canonical suites (``first_run``, ``bug_fix``, ``feature``, ``large_repo``,
``security``, ``regression``) speak the same numbers when comparing a case
against a baseline (UVD-016 marketplace benchmark-on-install + UVD-018
benchmark first-run).

All metrics follow the textbook definitions:

- ``precision = tp / (tp + fp)``  (0.0 when no positive predictions)
- ``recall    = tp / (tp + fn)``  (0.0 when no relevant items)
- ``f1        = 2pr / (p + r)``   (0.0 when p or r is 0)
- ``mrr       = mean(1 / rank)``  (ranks of 0 contribute 0.0)

The :class:`EvalScore` dataclass is frozen so accidental mutation of a
returned report (e.g. by a test or a downstream consumer) raises immediately.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class EvalScore:
    """A single, immutable retrieval-quality score bundle.

    Attributes
    ----------
    precision, recall, f1:
        Standard binary-retrieval metrics, each in ``[0.0, 1.0]``.
    mrr:
        Mean reciprocal rank of the FIRST relevant item across the suite;
        ``0.0`` when no relevant item was retrieved or when ranks are empty.
    """

    precision: float
    recall: float
    f1: float
    mrr: float


class ScoreCalculator:
    """Computes :class:`EvalScore` from a confusion matrix OR a ranked prediction.

    Two usage modes:

    1. **From counts** (the static helpers) — used by deterministic test
       harnesses that already know ``tp / fp / fn`` and ranks.
    2. **From retrieval sets** (:meth:`compute`) — used by retrieval-style
       evals that have a set of relevant ids and a ranked list of
       predicted ids.
    """

    # ── Static helpers (operate on counts / ranks) ──────────────────────

    @staticmethod
    def precision(true_positives: int, false_positives: int) -> float:
        """``tp / (tp + fp)``; returns ``0.0`` when no positive predictions."""
        denom = true_positives + false_positives
        if denom <= 0:
            return 0.0
        return true_positives / denom

    @staticmethod
    def recall(true_positives: int, false_negatives: int) -> float:
        """``tp / (tp + fn)``; returns ``0.0`` when no relevant items."""
        denom = true_positives + false_negatives
        if denom <= 0:
            return 0.0
        return true_positives / denom

    @staticmethod
    def f1(precision: float, recall: float) -> float:
        """Harmonic mean; returns ``0.0`` when either input is ``0.0``."""
        if precision <= 0.0 or recall <= 0.0:
            return 0.0
        return 2.0 * precision * recall / (precision + recall)

    @staticmethod
    def mrr(ranks: Iterable[int]) -> float:
        """Mean reciprocal rank.

        A rank of ``0`` means "no relevant doc found" and contributes ``0.0`` to
        the mean (avoids division by zero). An empty input also yields ``0.0``.
        """
        recip = [0.0 if r <= 0 else 1.0 / r for r in ranks]
        if not recip:
            return 0.0
        return sum(recip) / len(recip)

    # ── Combined: compute a full EvalScore in one call ──────────────────

    def compute(
        self,
        y_true: Iterable[str],
        y_pred: Iterable[str],
        *,
        ranks: Iterable[int] | None = None,
    ) -> EvalScore:
        """Compute precision / recall / F1 / MRR in a single pass.

        Parameters
        ----------
        y_true:
            Iterable of relevant item ids (set or list).
        y_pred:
            ORDERED iterable of predicted item ids (used both for set-based
            precision/recall and — unless ``ranks`` is given — for MRR via the
            position of the first relevant hit).
        ranks:
            Optional explicit reciprocal-rank input. When ``None`` (the
            default), MRR is derived from ``y_pred``: ``1 / position_of_first
            _relevant_item``, or ``0.0`` if no relevant item appears.
        """
        true_set = set(y_true)
        pred_list = list(y_pred)

        tp = 0
        fp = 0
        for item in pred_list:
            if item in true_set:
                tp += 1
            else:
                fp += 1
        fn = len(true_set) - tp

        p = self.precision(tp, fp)
        r = self.recall(tp, fn)
        f1 = self.f1(p, r)

        if ranks is not None:
            mrr_value = self.mrr(ranks)
        else:
            # First-hit rank from y_pred. 0 → no relevant hit.
            first_rank = 0
            for i, item in enumerate(pred_list, start=1):
                if item in true_set:
                    first_rank = i
                    break
            mrr_value = (1.0 / first_rank) if first_rank > 0 else 0.0

        return EvalScore(precision=p, recall=r, f1=f1, mrr=mrr_value)


__all__ = ["EvalScore", "ScoreCalculator"]

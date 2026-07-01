"""Runtime intel — confidence calibration via Brier score.

Lives in `runtime/intel/`. Layer L10. Extracted from `simulator.py` so
the calibration logic owns its own surface and a single Brier-style
score is the source of truth.

Drift rule: ``|brier - baseline| > 0.05`` → emit
``runtime.calibration.drift``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

DRIFT_EVENT = "runtime.calibration.drift"
DEFAULT_TOLERANCE = 0.05
DEFAULT_BASELINE = 0.25


@dataclass(frozen=True)
class CalibrationEntry:
    """A single observed (confidence, outcome) pair."""

    confidence: float
    outcome: float  # in [0, 1]


@dataclass
class CalibrationReport:
    """Brier-style calibration score plus drift verdict."""

    brier_score: float
    baseline: float
    brier_within_baseline: bool
    drift_event: str | None = None
    sample_size: int = 0

    @classmethod
    def build(
        cls,
        history: Iterable[CalibrationEntry],
        baseline: float = DEFAULT_BASELINE,
        tolerance: float = DEFAULT_TOLERANCE,
        on_drift: Callable[[str], None] | None = None,
    ) -> CalibrationReport:
        entries = list(history)
        if not entries:
            return cls(
                brier_score=0.0,
                baseline=baseline,
                brier_within_baseline=True,
                drift_event=None,
                sample_size=0,
            )
        brier = _brier_score(entries)
        within = abs(brier - baseline) <= tolerance
        drift: str | None = None
        if not within:
            drift = DRIFT_EVENT
            if on_drift is not None:
                on_drift(drift)
        return cls(
            brier_score=brier,
            baseline=baseline,
            brier_within_baseline=within,
            drift_event=drift,
            sample_size=len(entries),
        )


def _brier_score(entries: list[CalibrationEntry]) -> float:
    if not entries:
        return 0.0
    total = sum((e.confidence - e.outcome) ** 2 for e in entries)
    return total / len(entries)


class DriftDetected(Exception):
    """Raised when a build_run asks to raise on drift (opt-in)."""

    def __init__(self, brier: float, baseline: float) -> None:
        super().__init__(f"calibration drift: brier={brier:.4f} baseline={baseline:.4f}")
        self.brier = brier
        self.baseline = baseline


class ConfidenceCalibrator:
    """Facade over :class:`CalibrationReport`."""

    def build_report(
        self,
        history: Iterable[CalibrationEntry],
        baseline: float = DEFAULT_BASELINE,
        tolerance: float = DEFAULT_TOLERANCE,
        on_drift: Callable[[str], None] | None = None,
    ) -> CalibrationReport:
        return CalibrationReport.build(
            history, baseline=baseline, tolerance=tolerance, on_drift=on_drift
        )

    def calibrate(
        self,
        history: Iterable[CalibrationEntry],
        baseline: float = DEFAULT_BASELINE,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> float:
        # ponytail: `calibrate` returns the Brier score; drift surfaced via report
        return self.build_report(history, baseline=baseline, tolerance=tolerance).brier_score

    def raises_on_drift(
        self,
        history: Iterable[CalibrationEntry],
        baseline: float = DEFAULT_BASELINE,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> CalibrationReport:
        report = self.build_report(history, baseline=baseline, tolerance=tolerance)
        if report.drift_event is not None:
            raise DriftDetected(report.brier_score, baseline)
        return report

"""Tests for runtime.intel.calibration — Brier-score confidence calibration."""

from __future__ import annotations

import pytest

from opencontext_core.runtime.intel.calibration import (
    CalibrationEntry,
    CalibrationReport,
    ConfidenceCalibrator,
)


def _history(confidence: float, n: int = 100, outcome_seed: int = 0) -> list[CalibrationEntry]:
    """Build n well-calibrated entries: confidence matches outcome rate."""
    # For well-calibrated: outcomes follow Bernoulli(p) → Brier = p(1-p)
    out = []
    for _ in range(n):
        # deterministic outcome = confidence (always well-calibrated)
        out.append(CalibrationEntry(confidence=confidence, outcome=confidence))
    return out


def _overconfident_history(
    n: int = 100, confidence: float = 0.9, outcome: float = 0.5
) -> list[CalibrationEntry]:
    """confidence - outcome = 0.4 → Brier is 0.16, well over 0.05 tolerance."""
    return [CalibrationEntry(confidence=confidence, outcome=outcome) for _ in range(n)]


class TestCalibrationReportInBand:
    def test_perfectly_calibrated_is_in_band(self) -> None:
        # confidence == outcome → brier == 0, baseline 0 → in band
        history = [CalibrationEntry(confidence=0.0, outcome=0.0)] * 50 + [
            CalibrationEntry(confidence=1.0, outcome=1.0)
        ] * 50
        report = CalibrationReport.build(history, baseline=0.0)
        assert report.brier_within_baseline is True
        assert report.drift_event is None

    def test_stable_distribution_is_in_band(self) -> None:
        # confidence=0.5, outcome=0.0 → (0.5-0)^2 = 0.25 averaged → Brier=0.25
        history = [CalibrationEntry(confidence=0.5, outcome=0.0) for _ in range(100)]
        report = CalibrationReport.build(history, baseline=0.25)
        assert report.brier_within_baseline is True

    def test_brier_within_005_of_baseline(self) -> None:
        # Brier = 0.25, baseline = 0.25, diff = 0.0 → in band
        history = [CalibrationEntry(confidence=0.5, outcome=0.0) for _ in range(100)]
        report = CalibrationReport.build(history, baseline=0.25)
        assert report.brier_within_baseline is True


class TestCalibrationDrift:
    def test_overconfident_triggers_drift(self) -> None:
        # confidence=0.9, outcome=0.5 → Brier = 0.16, baseline=0.25, |diff|=0.09 > 0.05
        history = _overconfident_history()
        report = CalibrationReport.build(history, baseline=0.25)
        assert report.brier_within_baseline is False
        assert report.drift_event == "runtime.calibration.drift"

    def test_drift_emits_event(self) -> None:
        history = _overconfident_history()
        events: list[str] = []
        CalibrationReport.build(history, baseline=0.25, on_drift=events.append)
        assert "runtime.calibration.drift" in events

    def test_drift_within_tolerance_passes(self) -> None:
        # |0.08 - 0.05| → drift; |0.04| → in band. Use conf=0.7 outcome=0.5: Brier=0.04
        history = [CalibrationEntry(confidence=0.7, outcome=0.5) for _ in range(100)]
        report = CalibrationReport.build(history, baseline=0.04)
        assert report.brier_within_baseline is True


class TestCalibrationBrierMath:
    def test_brier_zero_when_perfect(self) -> None:
        history = [CalibrationEntry(confidence=1.0, outcome=1.0) for _ in range(10)]
        report = CalibrationReport.build(history)
        assert report.brier_score == 0.0

    def test_brier_max_when_worst(self) -> None:
        history = [CalibrationEntry(confidence=1.0, outcome=0.0) for _ in range(10)]
        report = CalibrationReport.build(history)
        assert report.brier_score == 1.0

    def test_empty_history_returns_neutral(self) -> None:
        report = CalibrationReport.build([])
        assert report.brier_score == 0.0
        assert report.brier_within_baseline is True
        assert report.drift_event is None


class TestConfidenceCalibratorFacade:
    def test_calibrate_returns_brier_score(self) -> None:
        cal = ConfidenceCalibrator()
        history = [CalibrationEntry(confidence=0.8, outcome=0.8) for _ in range(50)]
        score = cal.calibrate(history)
        assert score == pytest.approx(0.0)

    def test_build_report_delegates(self) -> None:
        cal = ConfidenceCalibrator()
        history = _overconfident_history()
        report = cal.build_report(history, baseline=0.25)
        assert report.brier_within_baseline is False

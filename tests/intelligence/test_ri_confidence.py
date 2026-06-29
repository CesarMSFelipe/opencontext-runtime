"""Confidence Engine — 8 dimensions + threshold→action (SPEC-RI-011-10/11)."""

from __future__ import annotations

from opencontext_core.models.intelligence import CONFIDENCE_DIMENSIONS
from opencontext_core.runtime_intelligence.confidence import (
    ConfidenceEngine,
    ConfidenceSignals,
)


def test_report_carries_all_eight_dimensions() -> None:
    engine = ConfidenceEngine()
    report = engine.report(
        session_id="s",
        run_id="r",
        workflow="oc-flow",
        signals=ConfidenceSignals(
            intent_confidence=0.7,
            context_coverage=0.7,
            plan_confidence=0.7,
            mutation_confidence=0.7,
            inspection_confidence=0.7,
            memory_hit_rate=0.7,
            policy_violation_rate=0.1,
        ),
    )
    assert set(report.dimensions) == set(CONFIDENCE_DIMENSIONS)
    assert 0.0 <= report.overall <= 1.0


def test_overall_below_ask_recommends_ask() -> None:
    # All seven sub-signals at 0.6 → overall 0.6; ask_below default 0.65,
    # switch_below 0.55 → action is "ask". Security/context are ≥0.5 so no
    # targeted short-circuit fires.
    engine = ConfidenceEngine()
    report = engine.report(
        session_id="s",
        run_id="r",
        workflow="oc-flow",
        signals=ConfidenceSignals(
            intent_confidence=0.6,
            context_coverage=0.6,
            plan_confidence=0.6,
            mutation_confidence=0.6,
            inspection_confidence=0.6,
            memory_hit_rate=0.6,
            policy_violation_rate=0.4,  # security = 0.6
        ),
    )
    assert abs(report.overall - 0.6) < 1e-6
    assert report.recommended_action == "ask"


def test_absent_signal_is_disclosed_not_invented() -> None:
    engine = ConfidenceEngine()
    report = engine.report(
        session_id="s", run_id="r", workflow="oc-flow", signals=ConfidenceSignals()
    )
    # Every dimension still present, and the defaults are disclosed in evidence.
    assert set(report.dimensions) == set(CONFIDENCE_DIMENSIONS)
    assert any(ref.startswith("default:") for ref in report.evidence_refs)


def test_recommend_only_does_not_mutate_inputs() -> None:
    engine = ConfidenceEngine()
    signals = ConfidenceSignals(intent_confidence=0.9)
    engine.report(session_id="s", run_id="r", workflow="oc-flow", signals=signals)
    # The engine recommends; it never mutates the caller's signals.
    assert signals.intent_confidence == 0.9


def test_low_security_short_circuits_to_require_approval() -> None:
    engine = ConfidenceEngine()
    report = engine.report(
        session_id="s",
        run_id="r",
        workflow="oc-flow",
        signals=ConfidenceSignals(
            intent_confidence=0.9,
            context_coverage=0.9,
            plan_confidence=0.9,
            mutation_confidence=0.9,
            inspection_confidence=0.9,
            memory_hit_rate=0.9,
            policy_violation_rate=0.8,  # security = 0.2 (critical)
        ),
    )
    assert report.recommended_action == "require_approval"

"""Convergence additions: optimizer, calibration, decision-quality (Phase CONV)."""

from __future__ import annotations

from types import SimpleNamespace

from opencontext_core.runtime.decisions import DecisionLog, RuntimeDecision
from opencontext_core.runtime_intelligence.health import (
    confidence_calibration_error,
    cost_calibration_error,
    decision_quality_metrics,
)
from opencontext_core.runtime_intelligence.optimizer import (
    LearningRuntimeOptimizer,
    RuntimeOptimizationRecommendation,
)


def test_optimizer_recommendation_is_propose_only_and_benchmark_gated() -> None:
    optimizer = LearningRuntimeOptimizer()
    budget = SimpleNamespace(
        operation_type="retrieval", recommended_budget=4000, confidence=0.8
    )
    recs = optimizer.recommend(optimized_budgets=[budget])
    assert recs and all(isinstance(r, RuntimeOptimizationRecommendation) for r in recs)
    for rec in recs:
        assert rec.requires_approval is True  # never auto-applied
        assert rec.required_benchmarks  # benchmark-gated promotion
        assert rec.target in {"cache", "context", "profile", "routing"}


def test_confidence_calibration_error_computed() -> None:
    # predicted vs observed success.
    err = confidence_calibration_error([(0.8, 1.0), (0.6, 0.0)])
    assert err is not None
    assert abs(err - 0.4) < 1e-9
    assert confidence_calibration_error([]) is None


def test_cost_calibration_error_computed() -> None:
    err = cost_calibration_error([20.0, -40.0])  # estimate_error_pct values
    assert err is not None
    assert abs(err - 0.3) < 1e-9  # mean abs(30%) → 0.30 fraction


def test_selector_accuracy_from_decision_log() -> None:
    log = DecisionLog()
    log.append(RuntimeDecision(kind="next_node", chosen="apply", reason="ok"))
    log.append(
        RuntimeDecision(
            kind="next_node", chosen="verify", reason="x", governed_by="state_machine"
        )
    )
    metrics = decision_quality_metrics(log)
    # One of two next_node recommendations was overridden → 0.5 acceptance.
    assert metrics["selector_accuracy"] == 0.5
    assert metrics["recommendation_acceptance"] == 0.5


def test_decision_quality_empty_log_is_not_measured() -> None:
    metrics = decision_quality_metrics(DecisionLog())
    assert metrics["selector_accuracy"] is None

"""Runtime Health (book §13) — 10-dimension self-health report.

Composes the existing :class:`~opencontext_core.indexing.graph_health.GraphHealthReport`
(KG freshness), the parity-gated efficiency benchmark trend, confidence/cost
calibration error, and decision-quality metrics over the PR-000.1 Decision Log
into one :class:`~opencontext_core.models.intelligence.RuntimeHealthReport`.

Honesty (B9 / AVH-016): a dimension with no wired evidence source is reported as
``UNMEASURED`` — it is listed in ``unmeasured_dimensions`` and EXCLUDED from
``dimensions`` and from the ``overall_score`` mean. Health is never flattered with
an invented neutral score, and the overall reflects only what was actually
measured (``collect_health_evidence`` supplies the real signals).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from opencontext_core.indexing.graph_health import GraphHealthReport, compute_graph_health
from opencontext_core.models.intelligence import (
    HEALTH_DIMENSIONS,
    RuntimeHealthReport,
)
from opencontext_core.runtime_intelligence import events as ri_events
from opencontext_core.runtime_intelligence import telemetry_layout

# Default KG database location relative to the project root.
_DEFAULT_KG_DB = ".storage/opencontext/context_graph.db"

_NEUTRAL = 0.5  # only used as the kg score for an unknown graph status (still a real read).
_CRITICAL = 0.4  # below this a measured dimension is a critical finding.

_GRAPH_STATUS_SCORE = {"healthy": 1.0, "degraded": 0.5, "empty": 0.1, "unavailable": 0.0}


def confidence_calibration_error(samples: Sequence[tuple[float, float]]) -> float | None:
    """Mean absolute error between predicted confidence and observed success.

    Each sample is ``(predicted_confidence, observed_success)`` where
    ``observed_success`` is 0.0/1.0 (or a success rate). Returns ``None`` for an
    empty sample set (no signal → not measured).
    """
    if not samples:
        return None
    return sum(abs(pred - obs) for pred, obs in samples) / len(samples)


def cost_calibration_error(estimate_error_pcts: Sequence[float]) -> float | None:
    """Mean absolute estimate error (fraction) from a set of ``estimate_error_pct``.

    Returns ``None`` for an empty set.
    """
    if not estimate_error_pcts:
        return None
    return sum(abs(e) for e in estimate_error_pcts) / len(estimate_error_pcts) / 100.0


def decision_quality_metrics(decision_log: object) -> dict[str, float | None]:
    """Decision-quality metrics over the PR-000.1 Decision Log (RI-CONV).

    * ``selector_accuracy`` — fraction of ``next_node`` selections accepted by the
      State Machine (``governed_by`` unset); an override means the recommendation
      was wrong/altered.
    * ``recommendation_acceptance`` — same, across all decision kinds.

    Both are honest acceptance proxies derived from real log evidence; they are
    ``None`` when there are no entries (not measured).
    """
    entries_obj: Any = getattr(decision_log, "entries", decision_log)
    entries = list(entries_obj or [])
    if not entries:
        return {"selector_accuracy": None, "recommendation_acceptance": None}

    def _accepted(items: list[Any]) -> float | None:
        if not items:
            return None
        accepted = sum(1 for d in items if getattr(d, "governed_by", None) is None)
        return accepted / len(items)

    next_node = [d for d in entries if str(getattr(d, "kind", "")) == "next_node"]
    return {
        "selector_accuracy": _accepted(next_node),
        "recommendation_acceptance": _accepted(entries),
    }


class RuntimeHealth:
    """Aggregate the ten health dimensions into a :class:`RuntimeHealthReport`."""

    def report(
        self,
        root: str | Path = ".",
        *,
        graph_health: GraphHealthReport | None = None,
        efficiency_all_sufficient: bool | None = None,
        decision_log: object | None = None,
        confidence_samples: Sequence[tuple[float, float]] | None = None,
        cost_error_pcts: Sequence[float] | None = None,
        policy_violation_rate: float | None = None,
        extra_signals: dict[str, float] | None = None,
        emit: bool = False,
    ) -> RuntimeHealthReport:
        """Build the 10-dimension report, composing existing health signals."""
        if graph_health is None:
            graph_health = compute_graph_health(Path(root) / _DEFAULT_KG_DB)

        signals = dict(extra_signals or {})
        dq = decision_quality_metrics(decision_log) if decision_log is not None else {}
        conf_err = confidence_calibration_error(confidence_samples or [])
        cost_err = cost_calibration_error(cost_error_pcts or [])

        # ``None`` => no evidence source wired for that dimension => UNMEASURED. The
        # kg score is always a real read of the KG store's status.
        raw: dict[str, float | None] = {
            "kg_freshness": _GRAPH_STATUS_SCORE.get(graph_health.status, _NEUTRAL),
            "memory_quality": signals.get("memory_quality"),
            "skill_catalog": signals.get("skill_catalog"),
            "harness_pass_rate": signals.get("harness_pass_rate"),
            "selector_accuracy": dq.get("selector_accuracy"),
            "cost_calibration": None if cost_err is None else 1.0 - cost_err,
            "confidence_calibration": None if conf_err is None else 1.0 - conf_err,
            "benchmark_trend": (
                None
                if efficiency_all_sufficient is None
                else (0.9 if efficiency_all_sufficient else 0.4)
            ),
            "policy_violations": (
                None if policy_violation_rate is None else 1.0 - policy_violation_rate
            ),
            "context_drift": signals.get("context_drift"),
        }

        dims: dict[str, float] = {}
        unmeasured: list[str] = []
        for name in HEALTH_DIMENSIONS:  # canonical order, exactly the ten dimensions.
            value = raw.get(name)
            if value is None:
                unmeasured.append(name)
            else:
                dims[name] = max(0.0, min(1.0, value))

        # Overall reflects ONLY measured dimensions (kg_freshness always qualifies),
        # so unmeasured axes no longer drag a fabricated ~0.5 into the score (B9).
        overall = round(sum(dims.values()) / len(dims), 4) if dims else 0.0
        critical = [name for name, score in dims.items() if score < _CRITICAL]

        recommendations: list[str] = []
        if graph_health.status != "healthy":
            recommendations.append(
                f"KG is '{graph_health.status}' — run `opencontext index .` to refresh"
            )
        for name in critical:
            recommendations.append(f"critical: '{name}' is low ({dims[name]:.2f})")
        if unmeasured:
            recommendations.append(
                "unmeasured (no evidence source): " + ", ".join(unmeasured)
            )

        report = RuntimeHealthReport(
            overall_score=overall,
            dimensions=dims,
            unmeasured_dimensions=unmeasured,
            critical_findings=critical,
            recommendations=recommendations,
        )
        if emit:
            telemetry_layout.write_health(report, root)
            telemetry_layout.append_event(
                ri_events.HEALTH_REPORTED,
                {"overall_score": overall, "critical_findings": critical},
                root,
            )
        return report


__all__ = [
    "RuntimeHealth",
    "confidence_calibration_error",
    "cost_calibration_error",
    "decision_quality_metrics",
]

"""Context quality scoring — the honest 5-dimension ContextScorer.

Scores a context pack across Completeness, Relevance, Token Efficiency, Safety, and
Freshness from a real :class:`RuntimeTrace` or :class:`ContextPackResult`, producing a
unified :class:`ContextScore`.

NOTE: the fabricated benchmark machinery that used to live here — ``score_custom``
(hardcoded ``relevance=100.0``), ``BUILTIN_CASES`` (fabricated ``setup`` dicts), and
the ``BenchmarkSuite`` runner over them — was EXCISED. The honest efficiency benchmark
(:mod:`opencontext_core.evaluation.efficiency`) measures real CON-vs-SIN cost under a
quality-parity gate and owns its own persistence/reporting. Only the genuinely honest
scorer (which derives relevance from the real selected/discarded ratio) and the v2
metric scaffolding remain here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

# ── Quality Dimensions ──────────────────────────────────────────────────────


class QualityDimension(StrEnum):
    """Dimensions evaluated in a context quality score."""

    COMPLETENESS = "completeness"
    RELEVANCE = "relevance"
    TOKEN_EFFICIENCY = "token_efficiency"
    SAFETY = "safety"
    FRESHNESS = "freshness"


DIMENSION_WEIGHTS: dict[QualityDimension, float] = {
    QualityDimension.COMPLETENESS: 0.30,
    QualityDimension.RELEVANCE: 0.25,
    QualityDimension.TOKEN_EFFICIENCY: 0.25,
    QualityDimension.SAFETY: 0.10,
    QualityDimension.FRESHNESS: 0.10,
}

DIMENSION_LABELS: dict[QualityDimension, str] = {
    QualityDimension.COMPLETENESS: "Completeness",
    QualityDimension.RELEVANCE: "Relevance",
    QualityDimension.TOKEN_EFFICIENCY: "Token Efficiency",
    QualityDimension.SAFETY: "Safety",
    QualityDimension.FRESHNESS: "Freshness",
}


# ── Context Score ───────────────────────────────────────────────────────────


@dataclass
class ContextScore:
    """Quality score for a single context pack."""

    overall: float  # 0-100
    dimensions: dict[QualityDimension, float]  # Per-dimension scores 0-100
    breakdown: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": round(self.overall, 1),
            "dimensions": {dim.value: round(score, 1) for dim, score in self.dimensions.items()},
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


# ── Context Scorer ──────────────────────────────────────────────────────────


def _generate_recommendations(dimensions: dict[QualityDimension, float]) -> list[str]:
    """Generate actionable improvement suggestions based on dimension scores."""
    recs = []
    if (
        QualityDimension.COMPLETENESS in dimensions
        and dimensions[QualityDimension.COMPLETENESS] < 70
    ):
        recs.append(
            f"Increase source coverage — completeness is "
            f"{dimensions[QualityDimension.COMPLETENESS]:.0f}%. "
            "Consider expanding retrieval to include more relevant symbols and dependencies."
        )
    if QualityDimension.RELEVANCE in dimensions and dimensions[QualityDimension.RELEVANCE] < 70:
        recs.append(
            f"High noise detected (relevance: {dimensions[QualityDimension.RELEVANCE]:.0f}%) — "
            "consider stricter relevance filtering or adjusting the query."
        )
    if (
        QualityDimension.TOKEN_EFFICIENCY in dimensions
        and dimensions[QualityDimension.TOKEN_EFFICIENCY] < 70
    ):
        recs.append(
            f"Token efficiency is low ({dimensions[QualityDimension.TOKEN_EFFICIENCY]:.0f}%) — "
            "enable context compression or reduce included sources."
        )
    if QualityDimension.SAFETY in dimensions and dimensions[QualityDimension.SAFETY] < 100:
        recs.append(
            f"Safety score is {dimensions[QualityDimension.SAFETY]:.0f}% — "
            "review context for PII, secrets, or sensitive content."
        )
    if QualityDimension.FRESHNESS in dimensions and dimensions[QualityDimension.FRESHNESS] < 50:
        recs.append(
            f"Context freshness is low ({dimensions[QualityDimension.FRESHNESS]:.0f}%) — "
            "re-index the project to ensure context reflects the current codebase."
        )
    return recs


class ContextScorer:
    """Scores context packs across 5 quality dimensions from real evidence.

    Relevance is derived from the actual selected/discarded ratio of a real trace or
    pack — there is no hardcoded score. (The fabricated ``score_custom`` path was
    removed; cost is now measured by the efficiency benchmark.)
    """

    def score_from_trace(
        self,
        trace: Any,  # RuntimeTrace
        baseline_tokens: int = 0,
    ) -> ContextScore:
        """Compute quality score from a RuntimeTrace."""
        total_tokens = sum(trace.token_estimates.values()) if trace.token_estimates else 0
        n_selected = len(trace.selected_context_items)
        n_discarded = len(trace.discarded_context_items)

        # Completeness: what fraction of candidates were included
        total_candidates = n_selected + n_discarded
        coverage = n_selected / total_candidates if total_candidates > 0 else 1.0
        completeness = min(100.0, coverage * 100)
        if coverage > 0.8:
            completeness = min(100.0, completeness + 10)

        # Relevance: 1 - (discarded / total)
        noise_ratio = n_discarded / total_candidates if total_candidates > 0 else 0
        relevance = max(0, 100 * (1 - noise_ratio))

        # Token efficiency vs baseline
        if baseline_tokens > 0:
            reduction = (baseline_tokens - total_tokens) / baseline_tokens
            efficiency = min(100.0, max(0, 100 * reduction))
        else:
            efficiency = 50.0  # neutral when no baseline

        # Safety: assume clean unless trace has safety findings
        safety = 100.0
        meta_safety = trace.metadata.get("safety_findings", [])
        if meta_safety:
            safety = max(0, 100 - len(meta_safety) * 30)

        # Freshness: based on trace age
        age_hours = self._age_hours(trace.created_at)
        freshness = self._freshness_from_age(age_hours)

        dimensions = {
            QualityDimension.COMPLETENESS: completeness,
            QualityDimension.RELEVANCE: relevance,
            QualityDimension.TOKEN_EFFICIENCY: efficiency,
            QualityDimension.SAFETY: safety,
            QualityDimension.FRESHNESS: freshness,
        }

        overall = self._weighted_score(dimensions)
        recommendations = _generate_recommendations(dimensions)

        return ContextScore(
            overall=overall,
            dimensions=dimensions,
            breakdown={
                "total_tokens": total_tokens,
                "selected_items": n_selected,
                "discarded_items": n_discarded,
                "baseline_tokens": baseline_tokens,
                "age_hours": round(age_hours, 1),
            },
            recommendations=recommendations,
            metadata={"source": "trace", "workflow": trace.workflow_name, "model": trace.model},
        )

    def score_from_pack(
        self,
        pack: Any,  # ContextPackResult
        repo_root: str = ".",
        has_pii: bool = False,
        age_hours: float = 0,
    ) -> ContextScore:
        """Compute quality score from a ContextPackResult."""
        n_included = len(pack.included)
        n_omitted = len(pack.omitted)
        total = n_included + n_omitted

        coverage = n_included / total if total > 0 else 1.0
        completeness = min(100.0, coverage * 100)
        if coverage > 0.8:
            completeness = min(100.0, completeness + 10)

        noise_ratio = n_omitted / total if total > 0 else 0
        relevance = max(0, 100 * (1 - noise_ratio))

        if pack.available_tokens > 0:
            reduction = (pack.available_tokens - pack.used_tokens) / pack.available_tokens
            efficiency = min(100.0, max(0, 100 * reduction))
        else:
            efficiency = 50.0

        safety = 100.0 if not has_pii else 70.0
        freshness = self._freshness_from_age(age_hours)

        dimensions = {
            QualityDimension.COMPLETENESS: completeness,
            QualityDimension.RELEVANCE: relevance,
            QualityDimension.TOKEN_EFFICIENCY: efficiency,
            QualityDimension.SAFETY: safety,
            QualityDimension.FRESHNESS: freshness,
        }

        overall = self._weighted_score(dimensions)
        recommendations = _generate_recommendations(dimensions)

        return ContextScore(
            overall=overall,
            dimensions=dimensions,
            breakdown={
                "included": n_included,
                "omitted": n_omitted,
                "used_tokens": pack.used_tokens,
                "available_tokens": pack.available_tokens,
                "age_hours": round(age_hours, 1),
            },
            recommendations=recommendations,
            metadata={"source": "context_pack"},
        )

    @staticmethod
    def _age_hours(created_at: datetime) -> float:
        """Calculate age in hours from a datetime."""
        now = datetime.now(created_at.tzinfo if created_at.tzinfo else None)
        delta = now - created_at
        return delta.total_seconds() / 3600

    @staticmethod
    def _freshness_from_age(age_hours: float) -> float:
        """Score freshness based on context age."""
        if age_hours < 1:
            return 100.0
        if age_hours < 24:
            return 100 - (age_hours / 24) * 50  # 50-100 range
        if age_hours < 168:  # 7 days
            return 50 - ((age_hours - 24) / 144) * 30  # 20-50 range
        return max(0, 20 - (age_hours - 168) / 720 * 20)  # 0-20 range (decays over 30 days)

    @staticmethod
    def _weighted_score(dimensions: dict[QualityDimension, float]) -> float:
        """Compute weighted overall score from dimension scores."""
        total = 0.0
        for dim, score in dimensions.items():
            weight = DIMENSION_WEIGHTS.get(dim, 0)
            total += score * weight
        return total


# ── v2 Quality Metrics Schema ───────────────────────────────────────────────

V2_QUALITY_METRICS: dict[str, object] = {
    "context_contract_completeness": 0.0,  # % contracts with is_complete() == True
    "validation_gate_pass_rate": 0.0,  # % gates that passed
    "memory_hit_rate": 0.0,  # % memory retrievals in final pack
    "tier_distribution": {"cheap": 0, "precise": 0, "critical": 0},
}


def contract_build_latency_benchmark() -> dict[str, object]:
    """Measure time to build a ContextContract. Returns timing metadata."""
    import time

    try:
        from opencontext_core.context.planning.classifier import TaskClassifier
        from opencontext_core.context.planning.contract import ContextContractBuilder
        from opencontext_core.context.planning.risk import RiskClassifier

        start = time.monotonic()
        ContextContractBuilder(
            classifier=TaskClassifier(),
            risk_classifier=RiskClassifier(),
        ).build("benchmark: fix bug in payment service")
        elapsed_ms = (time.monotonic() - start) * 1000
        return {
            "scenario": "contract_build_latency",
            "duration_ms": round(elapsed_ms, 2),
            "status": "ok",
        }
    except Exception as exc:
        return {
            "scenario": "contract_build_latency",
            "duration_ms": -1.0,
            "status": "error",
            "error": str(exc),
        }

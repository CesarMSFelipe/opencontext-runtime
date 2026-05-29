"""Context Benchmark Suite — standardized quality scoring and benchmarking.

Measures context packs across 5 dimensions (Completeness, Relevance,
Token Efficiency, Safety, Freshness) and produces a unified ContextScore.
Includes a built-in benchmark suite for reproducible quality assessment.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

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
    """Scores context packs across 5 quality dimensions."""

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

    def score_custom(
        self,
        *,
        sources: list[str],
        tokens: int,
        baseline_tokens: int = 0,
        has_pii: bool = False,
        age_hours: float = 0,
    ) -> ContextScore:
        """Compute quality score from raw parameters (no trace/pack needed)."""
        completeness = 100.0 if sources else 0.0
        relevance = 100.0
        efficiency = (
            min(100.0, max(0, 100 * (baseline_tokens - tokens) / baseline_tokens))
            if baseline_tokens > 0
            else 50.0
        )
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
        return ContextScore(
            overall=overall,
            dimensions=dimensions,
            breakdown={
                "sources": len(sources),
                "tokens": tokens,
                "baseline_tokens": baseline_tokens,
                "age_hours": round(age_hours, 1),
            },
            recommendations=_generate_recommendations(dimensions),
            metadata={"source": "custom"},
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


# ── Benchmark Cases ─────────────────────────────────────────────────────────


@dataclass
class BenchmarkCase:
    """A single benchmark case for context quality evaluation."""

    id: str
    name: str
    description: str
    category: str  # completeness | relevance | efficiency | safety | freshness
    setup: dict[str, Any]
    expected_min_score: float  # 0-100
    tags: list[str] = field(default_factory=list)


BUILTIN_CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        id="completeness/minimal",
        name="Minimal Completeness",
        description="Single source file, simple query. Expects full coverage.",
        category="completeness",
        setup={"sources": ["src/main.py"], "tokens": 500, "baseline_tokens": 2500},
        expected_min_score=85,
        tags=["basic", "completeness"],
    ),
    BenchmarkCase(
        id="completeness/multi_file",
        name="Multi-file Coverage",
        description="Cross-file symbols query. Needs good retrieval coverage.",
        category="completeness",
        setup={
            "sources": ["src/api.py", "src/models.py", "src/db.py"],
            "tokens": 1500,
            "baseline_tokens": 3000,
        },
        expected_min_score=70,
        tags=["coverage", "retrieval"],
    ),
    BenchmarkCase(
        id="relevance/focused",
        name="Focused Relevance",
        description="Specific API question. Should exclude unrelated files.",
        category="relevance",
        setup={"sources": ["src/api/routes.py"], "tokens": 800, "baseline_tokens": 10000},
        expected_min_score=85,
        tags=["relevance", "precision"],
    ),
    BenchmarkCase(
        id="efficiency/large_project",
        name="Large Project Efficiency",
        description="Large codebase context. Expects >80% token reduction.",
        category="efficiency",
        setup={"sources": ["src/**/*.py"], "tokens": 2000, "baseline_tokens": 50000},
        expected_min_score=80,
        tags=["efficiency", "compression"],
    ),
    BenchmarkCase(
        id="safety/clean_context",
        name="Clean Context Safety",
        description="No PII or secrets. Expects perfect safety score.",
        category="safety",
        setup={
            "sources": ["src/utils.py"],
            "tokens": 300,
            "baseline_tokens": 1500,
            "has_pii": False,
        },
        expected_min_score=90,
        tags=["safety", "pii"],
    ),
    BenchmarkCase(
        id="freshness/recent",
        name="Recent Context Freshness",
        description="Context created less than 1 hour ago. Expects max freshness.",
        category="freshness",
        setup={"sources": ["src/main.py"], "tokens": 400, "baseline_tokens": 800, "age_hours": 0.5},
        expected_min_score=85,
        tags=["freshness", "recency"],
    ),
    BenchmarkCase(
        id="freshness/stale",
        name="Stale Context Penalty",
        description="Context is days old. Freshness should be low.",
        category="freshness",
        setup={"sources": ["src/main.py"], "tokens": 400, "baseline_tokens": 800, "age_hours": 72},
        expected_min_score=30,
        tags=["freshness", "staleness"],
    ),
]


# ── Benchmark Suite Runner ──────────────────────────────────────────────────


@dataclass
class BenchmarkCaseResult:
    """Result of running one benchmark case."""

    case_id: str
    passed: bool
    score: ContextScore
    details: str
    duration_ms: float


@dataclass
class BenchmarkSuiteResult:
    """Aggregate result for a benchmark suite run."""

    timestamp: str
    total_cases: int
    passed: int
    failed: int
    average_score: float
    results: list[BenchmarkCaseResult]
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "summary": {
                "total": self.total_cases,
                "passed": self.passed,
                "failed": self.failed,
                "average_score": round(self.average_score, 1),
            },
            "recommendations": self.recommendations,
            "results": [
                {
                    "case_id": r.case_id,
                    "passed": r.passed,
                    "score": r.score.to_dict(),
                    "details": r.details,
                    "duration_ms": round(r.duration_ms, 1),
                }
                for r in self.results
            ],
        }


class BenchmarkSuite:
    """Runs benchmark cases against the ContextScorer."""

    def __init__(self, scorer: ContextScorer | None = None):
        self.scorer = scorer or ContextScorer()
        self._cases = list(BUILTIN_CASES)

    def list_cases(self, category: str | None = None) -> list[BenchmarkCase]:
        """List available benchmark cases, optionally filtered by category."""
        if category:
            return [c for c in self._cases if c.category == category]
        return list(self._cases)

    def run(
        self,
        case_ids: list[str] | None = None,
        verbose: bool = False,
    ) -> BenchmarkSuiteResult:
        """Run specific benchmark cases by ID, or all if None."""
        cases = self._cases
        if case_ids:
            case_map = {c.id: c for c in self._cases}
            cases = [case_map[cid] for cid in case_ids if cid in case_map]
            if not cases:
                raise ValueError(f"No matching cases for IDs: {case_ids}")

        results: list[BenchmarkCaseResult] = []
        for case in cases:
            start = time.monotonic()
            try:
                score = self.scorer.score_custom(**case.setup)
                passed = score.overall >= case.expected_min_score
                detail = (
                    f"Score {score.overall:.1f} >= {case.expected_min_score}: "
                    f"{'PASS' if passed else 'FAIL'}"
                )
            except Exception as exc:
                score = ContextScore(
                    overall=0.0,
                    dimensions={},
                    recommendations=[],
                    metadata={},
                )
                passed = False
                detail = f"Error: {exc}"
            duration = (time.monotonic() - start) * 1000
            results.append(
                BenchmarkCaseResult(
                    case_id=case.id,
                    passed=passed,
                    score=score,
                    details=detail,
                    duration_ms=duration,
                )
            )
            if verbose:
                print(f"  {case.id:40} {detail} ({duration:.0f}ms)")

        passed_count = sum(1 for r in results if r.passed)
        avg_score = sum(r.score.overall for r in results) / len(results) if results else 0
        all_recs: list[str] = []
        for r in results:
            all_recs.extend(r.score.recommendations)
        # Deduplicate
        seen: set[str] = set()
        unique_recs: list[str] = []
        for rec in all_recs:
            if rec not in seen:
                seen.add(rec)
                unique_recs.append(rec)

        return BenchmarkSuiteResult(
            timestamp=datetime.now().isoformat(),
            total_cases=len(results),
            passed=passed_count,
            failed=len(results) - passed_count,
            average_score=avg_score,
            results=results,
            recommendations=unique_recs[:10],  # Top 10
        )

    def run_all(self, verbose: bool = False) -> BenchmarkSuiteResult:
        """Run all available benchmark cases."""
        return self.run(verbose=verbose)


# ── Output Formatting ───────────────────────────────────────────────────────


def format_benchmark_result(result: BenchmarkSuiteResult) -> str:
    """Format benchmark results as a human-readable string."""
    lines = [
        "+---------------------------------------------+",
        "|        OpenContext Benchmark Results         |",
        "+---------------------------------------------+",
        f"Timestamp: {result.timestamp}",
        "",
        f"Summary: {result.passed}/{result.total_cases} passed | "
        f"Avg score: {result.average_score:.1f}/100",
        "",
    ]
    for r in result.results:
        icon = "PASS" if r.passed else "FAIL"
        lines.append(
            f"  [{icon}] {r.case_id:40} {r.score.overall:5.1f}/100  ({r.duration_ms:.0f}ms)"
        )
        for dim, score in r.score.dimensions.items():
            bar = "#" * int(score / 10) + "-" * (10 - int(score / 10))
            lines.append(f"      {DIMENSION_LABELS.get(dim, dim.value):20} {bar} {score:.0f}")
        lines.append("")

    if result.recommendations:
        lines.append("Recommendations:")
        for rec in result.recommendations:
            lines.append(f"  -> {rec}")

    return "\n".join(lines)


def format_benchmark_result_json(result: BenchmarkSuiteResult) -> str:
    """Format benchmark results as JSON."""
    return json.dumps(result.to_dict(), indent=2)


# ── Persistence ─────────────────────────────────────────────────────────────

BENCHMARK_DIR = ".opencontext/benchmarks"


def save_result(
    result: BenchmarkSuiteResult,
    directory: str | Path = BENCHMARK_DIR,
) -> Path:
    """Save benchmark result as a timestamped JSON file.

    Returns:
        Path to the written file.
    """
    dest = Path(directory)
    dest.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = dest / f"{timestamp}-results.json"
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return path


def load_last_result(directory: str | Path = BENCHMARK_DIR) -> BenchmarkSuiteResult | None:
    """Load the most recent benchmark result from a directory.

    Returns:
        BenchmarkSuiteResult if any results exist, else None.
    """
    dest = Path(directory)
    if not dest.exists():
        return None
    files = sorted(dest.glob("*-results.json"), reverse=True)
    if not files:
        return None
    data = json.loads(files[0].read_text(encoding="utf-8"))
    return BenchmarkSuiteResult(
        timestamp=data["timestamp"],
        total_cases=data["summary"]["total"],
        passed=data["summary"]["passed"],
        failed=data["summary"]["failed"],
        average_score=data["summary"]["average_score"],
        results=_results_from_dict(data.get("results", [])),
        recommendations=data.get("recommendations", []),
    )


def _results_from_dict(results: list[dict[str, object]]) -> list[BenchmarkCaseResult]:
    """Deserialize a list of result dicts into BenchmarkCaseResult objects."""
    parsed: list[BenchmarkCaseResult] = []
    for r in results:
        score_data = cast(dict[str, object], r.get("score") or {})
        overall = cast(float, score_data.get("overall") or 0)
        dimensions_raw = cast(dict[str, object], score_data.get("dimensions") or {})
        recommendations_raw = cast(list[object], score_data.get("recommendations") or [])
        metadata_raw = cast(dict[str, object], score_data.get("metadata") or {})
        score = ContextScore(
            overall=overall,
            dimensions={
                QualityDimension(str(k)): float(cast(float, v)) for k, v in dimensions_raw.items()
            },
            recommendations=[str(x) for x in recommendations_raw],
            metadata=metadata_raw,
        )
        parsed.append(
            BenchmarkCaseResult(
                case_id=str(cast(str, r.get("case_id") or "")),
                passed=bool(r.get("passed", False)),
                score=score,
                details=str(cast(str, r.get("details") or "")),
                duration_ms=float(cast(float, r.get("duration_ms") or 0)),
            )
        )
    return parsed


# ── Markdown Report ─────────────────────────────────────────────────────────


def format_benchmark_report_markdown(
    result: BenchmarkSuiteResult,
    output_path: str | Path | None = None,
) -> str:
    """Generate a self-contained markdown benchmark report.

    If output_path is given, also writes to that file.
    """
    lines = [
        "# OpenContext Benchmark Report",
        "",
        f"**Timestamp**: {result.timestamp}",
        f"**Summary**: {result.passed}/{result.total_cases} passed | "
        f"Average score: {result.average_score:.1f}/100",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total cases | {result.total_cases} |",
        f"| Passed | {result.passed} |",
        f"| Failed | {result.failed} |",
        f"| Average score | {result.average_score:.1f} |",
        "",
    ]
    if result.recommendations:
        lines.extend(["## Recommendations", ""])
        for rec in result.recommendations:
            lines.append(f"- {rec}")
        lines.append("")

    lines.extend(["## Per-Case Results", ""])
    for r in result.results:
        icon = "✅" if r.passed else "❌"
        lines.append(f"### {icon} {r.case_id}: {r.score.overall:.1f}/100 ({r.duration_ms:.0f}ms)")
        lines.append("")
        lines.append("| Dimension | Score |")
        lines.append("|-----------|-------|")
        for dim, score in r.score.dimensions.items():
            label = DIMENSION_LABELS.get(dim, dim.value)
            lines.append(f"| {label} | {score:.0f}/100 |")
        lines.append(f"\n{r.details}\n")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(report, encoding="utf-8")

    return report


def compare_results(
    before: BenchmarkSuiteResult,
    after: BenchmarkSuiteResult,
) -> str:
    """Compare two benchmark runs and return a diff-style comparison."""
    lines = [
        "Benchmark Comparison",
        "═══════════════════════",
        f"{'Case':40} {'Before':>10} {'After':>10} {'Δ':>10}",
        "─" * 75,
    ]
    before_map = {r.case_id: r for r in before.results}
    after_map = {r.case_id: r for r in after.results}

    all_ids = list(dict.fromkeys(list(before_map.keys()) + list(after_map.keys())))
    for cid in all_ids:
        b = before_map.get(cid)
        a = after_map.get(cid)
        b_score = b.score.overall if b else 0
        a_score = a.score.overall if a else 0
        delta = a_score - b_score
        delta_str = f"+{delta:.1f}" if delta > 0 else f"{delta:.1f}"
        arrow = "↑" if delta > 2 else ("↓" if delta < -2 else "→")
        lines.append(f"{cid:40} {b_score:>8.1f}   {a_score:>8.1f}   {delta_str:>6} {arrow}")

    total_before = before.average_score
    total_after = after.average_score
    total_delta = total_after - total_before
    lines.append("─" * 75)
    lines.append(
        f"{'Average':40} {total_before:>8.1f}   {total_after:>8.1f}   {total_delta:>+6.1f}"
    )

    return "\n".join(lines)

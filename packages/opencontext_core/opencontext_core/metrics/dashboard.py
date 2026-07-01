"""metrics.dashboard — REQ-metrics-dash-001..004 KPI schema + dashboard.

Ponytail note: the spec calls for 13 KPIs; this is a single-file
implementation.  No async, no I/O, no external deps — CI-tracking JSONL is
deliberately delegated to PR-017 (out-of-scope here).
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime


# REQ-metrics-dash-001 — KPI enum, exactly 13 entries.
class KPI(enum.StrEnum):
    TIME_TO_FIRST_SUCCESS_MINUTES = "time_to_first_success_minutes"
    TASK_SUCCESS_RATE = "task_success_rate"
    TOKENS_PER_TASK = "tokens_per_task"
    CACHE_HIT_RATE = "cache_hit_rate"
    FIRST_PASS_YIELD = "first_pass_yield"
    P50_LATENCY_S = "p50_latency_s"
    P95_LATENCY_S = "p95_latency_s"
    EVAL_SUITE_PASS_RATE = "eval_suite_pass_rate"
    REDACTION_FALSE_POSITIVE_RATE = "redaction_false_positive_rate"
    REDACTION_FALSE_NEGATIVE_RATE = "redaction_false_negative_rate"
    KG_RETRIEVAL_MRR = "kg_retrieval_mrr"
    MEMORY_USEFULNESS_SCORE = "memory_usefulness_score"
    COMPATIBILITY_VIOLATIONS = "compatibility_violations"


KPI_NAMES: tuple[str, ...] = tuple(k.value for k in KPI)


# REQ-metrics-dash-003 — CI records exactly these 4 mandatory KPIs
MANDATORY_CI_KPIS: tuple[str, ...] = (
    KPI.TASK_SUCCESS_RATE.value,
    KPI.EVAL_SUITE_PASS_RATE.value,
    KPI.COMPATIBILITY_VIOLATIONS.value,
    KPI.REDACTION_FALSE_NEGATIVE_RATE.value,
)


class MissingMethodologyError(ValueError):
    """REQ-metrics-dash-001 — ``OC-METRICS-MISSING-METHODOLOGY``."""


@dataclass
class MetricCard:
    """Single dashboard tile."""

    name: str
    value: float
    trend: str = "flat"
    threshold: float | None = None

    def is_below_threshold(self) -> bool:
        if self.threshold is None:
            return False
        return self.value < self.threshold


@dataclass
class MetricRecord:
    """REQ-metrics-dash-001 — single append-only metric record."""

    kpi: str
    value: float
    methodology_version: str
    run_id: str
    ts: datetime
    dims: dict[str, str] = field(default_factory=dict)


@dataclass
class MetricsSnapshot:
    """REQ-metrics-dash-001 — a snapshot pinned to one ``methodology_version``."""

    methodology_version: str
    records: list[MetricRecord] = field(default_factory=list)


@dataclass
class MetricsDashboard:
    """REQ-metrics-dash-002..004 — KPI schema + dashboard renderer."""

    methodology_version: str = "2026.07.01"

    # REQ-metrics-dash-001 -------------------------------------------------
    def record(
        self,
        kpi: str,
        value: float,
        methodology_version: str,
        run_id: str,
        ts: datetime,
        dims: dict[str, str] | None = None,
    ) -> MetricRecord:
        if not methodology_version:
            raise MissingMethodologyError(
                f"OC-METRICS-MISSING-METHODOLOGY: kpi={kpi} run_id={run_id}"
            )
        if kpi not in KPI_NAMES:
            raise ValueError(f"unknown kpi: {kpi!r}")
        return MetricRecord(
            kpi=kpi,
            value=float(value),
            methodology_version=methodology_version,
            run_id=run_id,
            ts=ts,
            dims=dict(dims or {}),
        )

    # REQ-metrics-dash-002 -------------------------------------------------
    def collect_metrics(self, samples: Mapping[str, float]) -> list[MetricCard]:
        cards: list[MetricCard] = []
        for kpi in KPI:
            value = float(samples.get(kpi.value, 0.0))
            threshold = _threshold_for(kpi)
            trend = "up" if value > threshold else "down" if value < threshold else "flat"
            cards.append(
                MetricCard(
                    name=kpi.value,
                    value=value,
                    trend=trend,
                    threshold=threshold,
                )
            )
        return cards

    # REQ-metrics-dash-002 -------------------------------------------------
    def render_dashboard(
        self,
        samples: Mapping[str, float],
        format: str = "md",
    ) -> str:
        if format not in {"md", "json", "html"}:
            return self._render_markdown(samples)
        if format == "json":
            return self._render_json(samples)
        if format == "html":
            return self._render_html(samples)
        return self._render_markdown(samples)

    # REQ-metrics-dash-004 -------------------------------------------------
    def build_snapshot(
        self,
        records: Iterable[tuple[str, float, str, str]],
    ) -> MetricsSnapshot:
        snap = MetricsSnapshot(methodology_version=self.methodology_version)
        for kpi, value, method, run_id in records:
            snap.records.append(
                MetricRecord(
                    kpi=kpi,
                    value=float(value),
                    methodology_version=method,
                    run_id=run_id,
                    ts=datetime.now(UTC),
                )
            )
        snap.methodology_version = _dominant_method(snap.records) or self.methodology_version
        return snap

    def render_with_methodology(self, snapshot: MetricsSnapshot) -> str:
        lines: list[str] = [
            "# OpenContext Metrics Dashboard",
            "",
            f"- methodology_version: **{snapshot.methodology_version}**",
            "",
        ]
        if _has_methodology_bump(snapshot.records):
            lines.append("> ⚠ **methodology change detected** — historical sparkline breaks here.")
            lines.append("")
        # Group by KPI
        by_kpi: dict[str, list[MetricRecord]] = {}
        for rec in snapshot.records:
            by_kpi.setdefault(rec.kpi, []).append(rec)
        for kpi in KPI_NAMES:
            if kpi not in by_kpi:
                continue
            latest = by_kpi[kpi][-1]
            lines.append(f"- **{kpi}** = {latest.value} (run `{latest.run_id}`)")
        return "\n".join(lines) + "\n"

    # ---------------------------------------------------------------------
    def _render_markdown(self, samples: Mapping[str, float]) -> str:
        lines: list[str] = [
            "# OpenContext Metrics Dashboard",
            "",
            f"- methodology_version: **{self.methodology_version}**",
            f"- kpi_count: **{len(KPI)}**",
            "",
            "## KPIs",
            "",
        ]
        for kpi in KPI:
            value = samples.get(kpi.value, 0.0)
            lines.append(f"- **{kpi.value}** = {value} _(sparkline placeholder)_")
        return "\n".join(lines) + "\n"

    def _render_json(self, samples: Mapping[str, float]) -> str:
        import json

        return json.dumps(
            {
                "methodology_version": self.methodology_version,
                "kpis": {
                    kpi.value: {
                        "value": samples.get(kpi.value, 0.0),
                        "threshold": _threshold_for(kpi),
                    }
                    for kpi in KPI
                },
            },
            sort_keys=True,
            indent=2,
        )

    def _render_html(self, samples: Mapping[str, float]) -> str:
        rows = "".join(
            f"<tr><td>{kpi.value}</td><td>{samples.get(kpi.value, 0.0)}</td></tr>" for kpi in KPI
        )
        return (
            "<html><body>"
            f"<h1>OpenContext Metrics Dashboard</h1>"
            f"<p>methodology_version: <b>{self.methodology_version}</b></p>"
            f"<table>{rows}</table>"
            "</body></html>"
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


# Default thresholds (purely advisory; tuned for the 1.0 dashboard tile).
_THRESHOLDS: dict[str, float] = {
    KPI.TIME_TO_FIRST_SUCCESS_MINUTES.value: 15.0,
    KPI.TASK_SUCCESS_RATE.value: 0.6,
    KPI.TOKENS_PER_TASK.value: 8000.0,
    KPI.CACHE_HIT_RATE.value: 0.5,
    KPI.FIRST_PASS_YIELD.value: 0.5,
    KPI.P50_LATENCY_S.value: 2.0,
    KPI.P95_LATENCY_S.value: 8.0,
    KPI.EVAL_SUITE_PASS_RATE.value: 0.8,
    KPI.REDACTION_FALSE_POSITIVE_RATE.value: 0.05,
    KPI.REDACTION_FALSE_NEGATIVE_RATE.value: 0.0,
    KPI.KG_RETRIEVAL_MRR.value: 0.6,
    KPI.MEMORY_USEFULNESS_SCORE.value: 0.6,
    KPI.COMPATIBILITY_VIOLATIONS.value: 0.0,
}


def _threshold_for(kpi: KPI) -> float:
    return _THRESHOLDS.get(kpi.value, 0.0)


def _dominant_method(records: Iterable[MetricRecord]) -> str | None:
    methods: list[str] = [r.methodology_version for r in records if r.methodology_version]
    if not methods:
        return None
    # Most-recent wins.
    return methods[-1]


def _has_methodology_bump(records: Iterable[MetricRecord]) -> bool:
    seen: set[str] = set()
    for rec in records:
        if rec.methodology_version and rec.methodology_version in seen:
            seen.add(rec.methodology_version)
        elif rec.methodology_version:
            if len(seen) > 0 and rec.methodology_version not in seen:
                return True
            seen.add(rec.methodology_version)
    # Use a simpler check: more than 1 distinct methodology.
    distinct = {r.methodology_version for r in records if r.methodology_version}
    return len(distinct) > 1


__all__ = [
    "KPI",
    "KPI_NAMES",
    "MANDATORY_CI_KPIS",
    "MetricCard",
    "MetricRecord",
    "MetricsDashboard",
    "MetricsSnapshot",
    "MissingMethodologyError",
]

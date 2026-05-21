"""Context Observability Pipeline — OpenTelemetry export, metrics, dashboard.

Records context usage metrics (tokens, cost, quality, latency) and exports
them to standard observability platforms via OpenTelemetry protocol (OTLP).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

from opencontext_core.models.trace import RuntimeTrace, TraceSpan

logger = logging.getLogger(__name__)


# ── Formatting Helpers ──────────────────────────────────────────────────────


def format_duration(ms: float) -> str:
    """Format milliseconds to human-readable duration."""
    if ms >= 60_000:
        return f"{ms / 60_000:.1f}m"
    if ms >= 1_000:
        return f"{ms / 1_000:.1f}s"
    if ms >= 1:
        return f"{ms:.0f}ms"
    return f"{ms * 1_000:.0f}µs"


def format_tokens(n: int) -> str:
    """Format token count to human-readable."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_cost(usd: float) -> str:
    """Format USD cost."""
    if usd >= 1:
        return f"${usd:.2f}"
    if usd >= 0.01:
        return f"${usd:.3f}"
    return f"${usd:.4f}"


# ── Metric Point ────────────────────────────────────────────────────────────


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    unit: str = ""


# ── OTel Exporter ───────────────────────────────────────────────────────────


def _to_rfc3339_nanos(dt: datetime | None) -> int:
    """Convert datetime to RFC3339 nanoseconds since epoch."""
    if dt is None:
        return int(time.time() * 1_000_000_000)
    epoch = dt.timestamp()
    return int(epoch * 1_000_000_000)


def _trace_to_otlp_json(trace: RuntimeTrace) -> dict[str, Any]:
    """Convert RuntimeTrace to OTLP-compatible JSON structure."""
    # Root span
    root_span = {
        "traceId": trace.trace_id,
        "spanId": trace.span_id,
        "parentSpanId": trace.parent_span_id or "",
        "name": trace.name,
        "kind": 1,  # SPAN_KIND_INTERNAL
        "startTimeUnixNano": str(_to_rfc3339_nanos(trace.start_time)),
        "endTimeUnixNano": str(_to_rfc3339_nanos(trace.end_time)),
        "attributes": [
            {"key": "workflow.name", "value": {"stringValue": trace.workflow_name}},
            {"key": "llm.provider", "value": {"stringValue": trace.provider}},
            {"key": "llm.model", "value": {"stringValue": trace.model}},
            {"key": "context.selected_items",
             "value": {"intValue": str(len(trace.selected_context_items))}},
            {"key": "context.discarded_items",
             "value": {"intValue": str(len(trace.discarded_context_items))}},
            {"key": "context.compression", "value": {"stringValue": trace.compression_strategy}},
            {"key": "service.name", "value": {"stringValue": "opencontext"}},
            {"key": "telemetry.sdk.name", "value": {"stringValue": "opencontext"}},
            {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
        ],
        "events": [
            {
                "timeUnixNano": str(_to_rfc3339_nanos(e.timestamp)),
                "name": e.name,
                "attributes": [
                    {"key": k, "value": {"stringValue": str(v)}}
                    for k, v in e.attributes.items()
                ],
            }
            for e in trace.events
        ],
        "status": {"code": 2 if trace.errors else 1},  # 2=Error, 1=OK
    }

    # Token estimates as events
    for key, val in trace.token_estimates.items():
        root_span["attributes"].append({
            "key": f"tokens.{key}",
            "value": {"intValue": str(val)},
        })

    # Timings as attributes
    for step, ms in trace.timings_ms.items():
        root_span["attributes"].append({
            "key": f"timing.{step}",
            "value": {"doubleValue": ms},
        })

    # Child spans
    child_spans = []
    for span in trace.spans:
        child = {
            "traceId": span.trace_id,
            "spanId": span.span_id,
            "parentSpanId": span.parent_span_id or trace.span_id,
            "name": span.name,
            "kind": 1,
            "startTimeUnixNano": str(_to_rfc3339_nanos(span.start_time)),
            "endTimeUnixNano": str(_to_rfc3339_nanos(span.end_time)),
            "attributes": [
                {"key": k, "value": {"stringValue": str(v)}}
                for k, v in span.attributes.items()
            ],
            "events": [
                {
                    "timeUnixNano": str(_to_rfc3339_nanos(e.timestamp)),
                    "name": e.name,
                    "attributes": [
                        {"key": k, "value": {"stringValue": str(v)}}
                        for k, v in e.attributes.items()
                    ],
                }
                for e in span.events
            ],
        }
        child_spans.append(child)

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "opencontext"}},
                        {"key": "telemetry.sdk.name", "value": {"stringValue": "opencontext"}},
                        {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "opencontext.traces"},
                        "spans": [root_span] + child_spans,
                    }
                ],
            }
        ]
    }


class OtelExporter:
    """Exports trace spans and metrics to an OpenTelemetry Collector via OTLP HTTP."""

    def __init__(
        self,
        endpoint: str = "http://localhost:4318",
        service_name: str = "opencontext",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.service_name = service_name
        self._enabled = True

    def export_trace(self, trace: RuntimeTrace) -> bool:
        """Export a RuntimeTrace as OTLP JSON to the collector.

        Returns True if export was attempted (even if it failed silently).
        Returns False if the exporter is disabled.
        """
        if not self._enabled:
            return False
        try:
            import urllib.request as req
            data = _trace_to_otlp_json(trace)
            body = json.dumps(data).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            url = f"{self.endpoint}/v1/traces"
            r = req.Request(url, data=body, headers=headers, method="POST")
            with req.urlopen(r, timeout=5) as resp:
                if resp.status != 200:
                    logger.debug("OTLP trace export returned %s", resp.status)
            return True
        except Exception as exc:
            logger.debug("OTLP trace export failed: %s", exc)
            return False

    def export_metrics(self, metrics: list[MetricPoint]) -> bool:
        """Export metric points to OTLP metrics endpoint."""
        if not self._enabled or not metrics:
            return False
        try:
            import urllib.request as req
            now_nano = _to_rfc3339_nanos(None)
            scope_metrics = []
            for m in metrics:
                attrs = [
                    {"key": k, "value": {"stringValue": str(v)}}
                    for k, v in m.attributes.items()
                ]
                dp = {
                    "timeUnixNano": str(now_nano),
                    "asDouble": m.value,
                }
                if attrs:
                    dp["attributes"] = attrs
                scope_metrics.append({
                    "name": m.name,
                    "unit": m.unit or "1",
                    "gauge": {"dataPoints": [dp]},
                })

            body = json.dumps({
                "resourceMetrics": [{
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": self.service_name}},
                        ]
                    },
                    "scopeMetrics": [{
                        "scope": {"name": "opencontext.metrics"},
                        "metrics": scope_metrics,
                    }],
                }],
            }).encode("utf-8")

            url = f"{self.endpoint}/v1/metrics"
            headers = {"Content-Type": "application/json"}
            r = req.Request(url, data=body, headers=headers, method="POST")
            with req.urlopen(r, timeout=5) as resp:
                if resp.status != 200:
                    logger.debug("OTLP metrics export returned %s", resp.status)
            return True
        except Exception as exc:
            logger.debug("OTLP metrics export failed: %s", exc)
            return False

    def disable(self) -> None:
        """Disable the exporter (e.g., if endpoint unreachable repeatedly)."""
        self._enabled = False


# ── Cost Estimation ─────────────────────────────────────────────────────────


_PROVIDER_RATES: dict[str, dict[str, float]] = {
    "openai": {"gpt-4": 0.03, "gpt-4-turbo": 0.01, "gpt-3.5-turbo": 0.0015, "gpt-4o": 0.005, "*": 0.003},
    "anthropic": {"claude-3-opus": 0.015, "claude-3-sonnet": 0.003, "claude-3-haiku": 0.00025, "claude-sonnet-4": 0.003, "*": 0.003},
    "google": {"gemini-pro": 0.00025, "*": 0.001},
    "mock": {"*": 0.0},
    "*": {"*": 0.002},
}


def estimate_cost(provider: str, model: str, tokens: int) -> float:
    """Estimate USD cost for a given provider/model/token count."""
    rates = _PROVIDER_RATES.get(provider, _PROVIDER_RATES.get("*", {}))
    rate = rates.get(model, rates.get("*", 0.002))
    return (tokens / 1_000) * rate


# ── Metrics Collector ───────────────────────────────────────────────────────


class MetricsCollector:
    """Collects and buffers context metrics for export."""

    def __init__(self, exporter: OtelExporter | None = None):
        self.exporter = exporter
        self._lock = threading.Lock()
        self._buffer: list[MetricPoint] = []

    def record_trace_metrics(self, trace: RuntimeTrace) -> None:
        """Extract and record metrics from a completed trace."""
        now = datetime.now().isoformat()

        # Token totals
        total_tokens = sum(trace.token_estimates.values()) if trace.token_estimates else 0
        self._add(MetricPoint("context.total_tokens", float(total_tokens), now, unit="1"))
        self._add(MetricPoint(
            "context.selected_items", float(len(trace.selected_context_items)), now, unit="1",
        ))
        self._add(MetricPoint(
            "context.discarded_items", float(len(trace.discarded_context_items)), now, unit="1",
        ))

        # Duration
        total_ms = sum(trace.timings_ms.values()) if trace.timings_ms else 0
        self._add(MetricPoint("workflow.duration_ms", total_ms, now, unit="ms"))

        # Errors
        error_count = float(len(trace.errors))
        self._add(MetricPoint("workflow.errors", error_count, now, unit="1",
                              attributes={"workflow": trace.workflow_name}))

        # Cost
        if trace.provider and total_tokens:
            cost = estimate_cost(trace.provider, trace.model, total_tokens)
            self._add(MetricPoint("cost.estimated_usd", cost, now, unit="usd",
                                  attributes={"provider": trace.provider, "model": trace.model}))

        # Workflow-specific
        self._add(MetricPoint("workflow.runs", 1.0, now, unit="1",
                              attributes={"workflow": trace.workflow_name}))

    def record_quality_score(self, score: float, details: dict[str, Any] | None = None) -> None:
        """Record a context quality score metric."""
        self._add(MetricPoint(
            "context.quality_score", score,
            attributes=details or {},
            unit="1",
        ))

    def flush(self) -> list[MetricPoint]:
        """Return all buffered points and clear the buffer."""
        with self._lock:
            points = list(self._buffer)
            self._buffer.clear()
        # Export if configured
        if self.exporter and points:
            self.exporter.export_metrics(points)
        return points

    def _add(self, point: MetricPoint) -> None:
        with self._lock:
            self._buffer.append(point)


# ── Dashboard ───────────────────────────────────────────────────────────────


class ContextDashboard:
    """Provides aggregated context metrics for the TUI dashboard."""

    def __init__(self, trace_logger: "LocalTraceLogger | None" = None):  # noqa: F821
        from opencontext_core.trace.logger import LocalTraceLogger
        self._logger = trace_logger or LocalTraceLogger()
        self._quality_scores: list[float] = []

    def record_quality(self, score: float) -> None:
        self._quality_scores.append(score)

    def show_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return summaries of recent traces."""
        try:
            traces = sorted(
                self._logger.base_path.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:limit]
            results = []
            for path in traces:
                try:
                    trace = self._logger.load(path.stem)
                    total_ms = sum(trace.timings_ms.values())
                    total_tokens = sum(trace.token_estimates.values()) if trace.token_estimates else 0
                    results.append({
                        "run_id": trace.run_id,
                        "workflow": trace.workflow_name,
                        "provider": trace.provider,
                        "model": trace.model,
                        "tokens": total_tokens,
                        "tokens_fmt": format_tokens(total_tokens),
                        "duration_ms": total_ms,
                        "duration_fmt": format_duration(total_ms),
                        "errors": len(trace.errors),
                        "created_at": trace.created_at.isoformat() if hasattr(trace.created_at, 'isoformat') else str(trace.created_at),
                    })
                except Exception:
                    continue
            return results
        except Exception:
            return []

    def show_timeline(self, hours: int = 24) -> dict[str, Any]:
        """Aggregate metrics per hour for the last N hours."""
        from datetime import timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        hourly: dict[str, dict] = {}
        total_traces = 0
        total_tokens = 0
        total_cost = 0.0
        error_count = 0

        try:
            for path in self._logger.base_path.glob("*.json"):
                try:
                    trace = self._logger.load(path.stem)
                    if trace.created_at.tzinfo is None:
                        from datetime import timezone as tz
                        created = trace.created_at.replace(tzinfo=tz.utc)
                    else:
                        created = trace.created_at
                    if created < cutoff:
                        continue
                    hour_key = created.strftime("%Y-%m-%dT%H:00")
                    if hour_key not in hourly:
                        hourly[hour_key] = {
                            "trace_count": 0, "total_tokens": 0, "total_duration": 0.0,
                            "error_count": 0, "total_cost": 0.0,
                        }
                    h = hourly[hour_key]
                    h["trace_count"] += 1
                    tok = sum(trace.token_estimates.values()) if trace.token_estimates else 0
                    h["total_tokens"] += tok
                    h["total_duration"] += sum(trace.timings_ms.values())
                    h["error_count"] += len(trace.errors)

                    total_traces += 1
                    total_tokens += tok
                    error_count += len(trace.errors)
                    if trace.provider and tok:
                        cost = estimate_cost(trace.provider, trace.model, tok)
                        h["total_cost"] += cost
                        total_cost += cost

                except Exception:
                    continue
        except Exception:
            pass

        return {
            "hours_tracked": hours,
            "total_traces": total_traces,
            "total_tokens": total_tokens,
            "total_tokens_fmt": format_tokens(total_tokens),
            "total_cost": total_cost,
            "total_cost_fmt": format_cost(total_cost),
            "error_count": error_count,
            "error_rate": error_count / total_traces if total_traces > 0 else 0,
            "hourly": hourly,
        }

    def show_health(self) -> dict[str, Any]:
        """Return health summary of the observability system."""
        total_traces = 0
        last_trace_time = ""
        top_workflows: dict[str, int] = {}
        error_count = 0

        try:
            traces = sorted(
                self._logger.base_path.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            total_traces = len(traces)
            for path in traces:
                try:
                    t = self._logger.load(path.stem)
                    if not last_trace_time:
                        last_trace_time = t.created_at.isoformat() if hasattr(t.created_at, 'isoformat') else str(t.created_at)
                    top_workflows[t.workflow_name] = top_workflows.get(t.workflow_name, 0) + 1
                    error_count += len(t.errors)
                except Exception:
                    continue
        except Exception:
            pass

        top_workflow = max(top_workflows, key=top_workflows.get) if top_workflows else "none"
        avg_quality = (
            sum(self._quality_scores) / len(self._quality_scores)
            if self._quality_scores else None
        )

        return {
            "total_traces_tracked": total_traces,
            "last_trace_at": last_trace_time,
            "average_quality_score": round(avg_quality, 1) if avg_quality is not None else None,
            "error_rate": round(error_count / total_traces, 3) if total_traces > 0 else 0,
            "top_workflow": top_workflow,
            "quality_scores_recorded": len(self._quality_scores),
        }

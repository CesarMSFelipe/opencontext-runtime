"""Canonical ``.opencontext/telemetry/`` layout + event/receipt sinks (OC-OBS).

The OC-OBS "Artifact Layout" wants a single telemetry directory::

    .opencontext/telemetry/
      events.jsonl            # append-only intelligence.* (and other) events
      traces.json             # trace snapshots
      metrics.json            # metric snapshots
      benchmark-history.json  # benchmark result history
      health.json             # last runtime-health report
      receipts.jsonl          # intelligence receipts (book §17)

This module is the authority for that layout. It writes the canonical files and
provides a legacy read shim for the pre-existing single-file
``.opencontext/telemetry.json`` so no history is orphaned. An optional, off-by-
default OpenTelemetry exporter renders the OTel-compatible
:class:`~opencontext_core.models.trace.RuntimeTrace` spans without requiring the
``opentelemetry`` package.

Events are append-only (OC-OBS invariant 1); writes never alter runtime
behaviour (invariant 6).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from opencontext_core.compat import UTC
from opencontext_core.runtime_intelligence.events import INTELLIGENCE_EVENT_FAMILY

# Canonical telemetry directory (relative to project root).
TELEMETRY_DIR = ".opencontext/telemetry"

EVENTS_FILE = "events.jsonl"
TRACES_FILE = "traces.json"
METRICS_FILE = "metrics.json"
BENCHMARK_HISTORY_FILE = "benchmark-history.json"
HEALTH_FILE = "health.json"
RECEIPTS_FILE = "receipts.jsonl"

# Legacy single-file telemetry (token-savings store) — read-shimmed, never deleted.
LEGACY_TELEMETRY_FILE = ".opencontext/telemetry.json"


def telemetry_dir(root: str | Path = ".") -> Path:
    """Return (creating) the canonical telemetry directory under *root*."""
    path = Path(root) / TELEMETRY_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def append_event(event: str, payload: dict[str, Any], root: str | Path = ".") -> Path:
    """Append one event line to ``telemetry/events.jsonl`` (append-only).

    The written record carries ``{timestamp, family, event, **payload}``. The
    ``family`` is the intelligence family for ``intelligence.*`` events.
    """
    path = telemetry_dir(root) / EVENTS_FILE
    record = {
        "timestamp": _now_iso(),
        "family": INTELLIGENCE_EVENT_FAMILY if event.startswith("intelligence.") else "runtime",
        "event": event,
        **payload,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return path


def append_receipt(kind: str, payload: dict[str, Any], root: str | Path = ".") -> Path:
    """Append one receipt line to ``telemetry/receipts.jsonl`` (book §17)."""
    path = telemetry_dir(root) / RECEIPTS_FILE
    record = {"timestamp": _now_iso(), "kind": kind, **payload}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
    return path


def read_events(root: str | Path = ".") -> list[dict[str, Any]]:
    """Read all canonical events (newest last). Returns ``[]`` when absent."""
    path = Path(root) / TELEMETRY_DIR / EVENTS_FILE
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def read_receipts(root: str | Path = ".") -> list[dict[str, Any]]:
    """Read all canonical receipts (newest last). Returns ``[]`` when absent."""
    path = Path(root) / TELEMETRY_DIR / RECEIPTS_FILE
    if not path.exists():
        return []
    receipts: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            receipts.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return receipts


def write_health(report: Any, root: str | Path = ".") -> Path:
    """Snapshot a runtime-health report to ``telemetry/health.json``."""
    path = telemetry_dir(root) / HEALTH_FILE
    data = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def append_benchmark_history(results: list[Any], root: str | Path = ".") -> Path:
    """Append a benchmark-run snapshot to ``telemetry/benchmark-history.json``."""
    path = telemetry_dir(root) / BENCHMARK_HISTORY_FILE
    history: list[Any] = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    snapshot = {
        "timestamp": _now_iso(),
        "results": [r.model_dump(mode="json") if hasattr(r, "model_dump") else r for r in results],
    }
    history.append(snapshot)
    path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
    return path


def read_legacy_telemetry(root: str | Path = ".") -> list[dict[str, Any]]:
    """Read the legacy single-file ``.opencontext/telemetry.json`` events.

    Back-compat shim so pre-canonical telemetry history is never orphaned.
    """
    path = Path(root) / LEGACY_TELEMETRY_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    events = data.get("events", []) if isinstance(data, dict) else []
    return [e for e in events if isinstance(e, dict)]


def export_otel(traces: list[Any], *, enabled: bool = False, root: str | Path = ".") -> str | None:
    """Optional OpenTelemetry exporter (off by default; OC-OBS DoD).

    When ``enabled`` is False (the default), returns ``None`` and writes nothing —
    observability must not alter behaviour. When enabled, renders the OTel-
    compatible spans of each :class:`RuntimeTrace` to an OTLP-shaped JSON file
    under the canonical layout WITHOUT requiring the ``opentelemetry`` package
    (the trace model is already OTel-shaped). Returns the written path as a string.
    """
    if not enabled:
        return None
    spans: list[dict[str, Any]] = []
    for trace in traces:
        # Root span.
        spans.append(
            {
                "traceId": getattr(trace, "trace_id", ""),
                "spanId": getattr(trace, "span_id", ""),
                "parentSpanId": getattr(trace, "parent_span_id", None),
                "name": getattr(trace, "name", "workflow.run"),
                "startTime": str(getattr(trace, "start_time", "")),
                "endTime": str(getattr(trace, "end_time", "")),
                "attributes": dict(getattr(trace, "attributes", {}) or {}),
            }
        )
        for span in getattr(trace, "spans", []) or []:
            spans.append(
                {
                    "traceId": getattr(span, "trace_id", ""),
                    "spanId": getattr(span, "span_id", ""),
                    "parentSpanId": getattr(span, "parent_span_id", None),
                    "name": getattr(span, "name", ""),
                    "startTime": str(getattr(span, "start_time", "")),
                    "endTime": str(getattr(span, "end_time", "")),
                    "attributes": dict(getattr(span, "attributes", {}) or {}),
                }
            )
    path = telemetry_dir(root) / "otel-spans.json"
    path.write_text(json.dumps({"spans": spans}, indent=2, default=str), encoding="utf-8")
    return str(path)


__all__ = [
    "BENCHMARK_HISTORY_FILE",
    "EVENTS_FILE",
    "HEALTH_FILE",
    "LEGACY_TELEMETRY_FILE",
    "METRICS_FILE",
    "RECEIPTS_FILE",
    "TELEMETRY_DIR",
    "TRACES_FILE",
    "append_benchmark_history",
    "append_event",
    "append_receipt",
    "export_otel",
    "read_events",
    "read_legacy_telemetry",
    "read_receipts",
    "telemetry_dir",
    "write_health",
]

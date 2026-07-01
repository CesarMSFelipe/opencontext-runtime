"""REQ-cli-v2-001: doctor --runtime returns 11-dim HealthReport."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


HEALTH_DIMENSIONS: tuple[str, ...] = (
    "runtime_core",
    "providers",
    "plugins",
    "marketplace",
    "knowledge_graph",
    "memory",
    "context_engine",
    "decision_log",
    "policy",
    "benchmarks",
    "studio",
)

SCHEMA_VERSION = "opencontext.health_report.v1"


def build_health_report(dimensions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dimensions": {d: dimensions.get(d, {"status": "unknown", "detail": ""})
                       for d in HEALTH_DIMENSIONS},
    }
"""REQ-cli-v2-001: simulate handler → SimulationReport-shaped dict."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "opencontext.simulation_report.v1"


def build_simulation_report(
    task: str,
    proposed_path: list[str],
    *,
    estimated_tokens: int | None = None,
    estimated_cost: float | None = None,
    estimated_duration_ms: int | None = None,
    estimator: str = "stub",
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "task": task,
        "proposed_path": list(proposed_path),
        "estimated_tokens": estimated_tokens,
        "estimated_cost": estimated_cost,
        "estimated_duration_ms": estimated_duration_ms,
        "estimator": estimator,
        "notes": list(notes or []),
        "generated_at": datetime.now(UTC).isoformat(),
    }
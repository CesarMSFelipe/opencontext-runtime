"""PR-014 Session dashboard — 10 fields."""

from __future__ import annotations

from typing import Any


DASHBOARD_FIELDS: tuple[str, ...] = (
    "session_id",
    "run_id",
    "workflow",
    "started_at",
    "elapsed_ms",
    "ok",
    "warnings",
    "errors",
    "artifacts",
    "decisions",
)


def render_dashboard(session: dict[str, Any]) -> dict[str, Any]:
    """Project a session dict onto the 10 dashboard fields."""
    return {f: session.get(f) for f in DASHBOARD_FIELDS}
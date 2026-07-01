"""PR-014 11 event-family lanes (CONV2 #12)."""

from __future__ import annotations

from typing import Any

# Eleven RuntimeEvent.family values (doc 59 §Event hierarchy).
LANE_FAMILIES: tuple[str, ...] = (
    "lifecycle",
    "workflow",
    "context",
    "memory",
    "kg",
    "runtime",
    "policy",
    "provider",
    "studio",
    "plugin",
    "benchmark",
)


def render_timeline(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group events by ``family`` and return one lane per family."""
    lanes: dict[str, list[dict[str, Any]]] = {f: [] for f in LANE_FAMILIES}
    for event in events:
        family = event.get("family")
        if family in lanes:
            lanes[family].append(event)
    return lanes

"""Studio — PR-014 dashboard, 11 timelines, 6 views."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TimelineEntry:
    timestamp: str
    event: str
    source: str


@dataclass
class StudioTimeline:
    name: str
    entries: list[TimelineEntry] = field(default_factory=list)


TIMELINE_NAMES = [
    "sdd-phases",
    "memory-saves",
    "conflicts",
    "judgments",
    "decisions",
    "benchmarks",
    "plugins",
    "providers",
    "cache-hits",
    "errors",
    "health",
]

VIEW_NAMES = ["dashboard", "sdd-flow", "memory-graph", "cost-breakdown", "health-radar", "timeline"]


class StudioServer:
    def status(self) -> dict[Any, Any]:
        return {"studio": "running", "timelines": len(TIMELINE_NAMES), "views": len(VIEW_NAMES)}

    def list_timelines(self) -> list[str]:
        return list(TIMELINE_NAMES)

    def list_views(self) -> list[str]:
        return list(VIEW_NAMES)

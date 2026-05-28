"""Token savings telemetry — tracks cumulative token reduction over time."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

TELEMETRY_FILE = ".opencontext/telemetry.json"


@dataclass
class TelemetryEvent:
    timestamp: float
    task: str
    naive_tokens: int
    optimized_tokens: int
    reduction_pct: float
    scenario: str = ""


@dataclass
class TelemetryStore:
    events: list[TelemetryEvent] = field(default_factory=list)

    @property
    def total_naive(self) -> int:
        return sum(e.naive_tokens for e in self.events)

    @property
    def total_optimized(self) -> int:
        return sum(e.optimized_tokens for e in self.events)

    @property
    def total_saved(self) -> int:
        return self.total_naive - self.total_optimized

    @property
    def average_reduction(self) -> float:
        if not self.events:
            return 0.0
        return sum(e.reduction_pct for e in self.events) / len(self.events)

    @property
    def session_count(self) -> int:
        return len(self.events)


def load_telemetry(root: str | Path = ".") -> TelemetryStore:
    path = Path(root) / TELEMETRY_FILE
    if not path.exists():
        return TelemetryStore()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return TelemetryStore(events=[TelemetryEvent(**e) for e in data.get("events", [])])
    except Exception:
        return TelemetryStore()


def record_event(event: TelemetryEvent, root: str | Path = ".") -> None:
    store = load_telemetry(root)
    store.events.append(event)
    path = Path(root) / TELEMETRY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"events": [asdict(e) for e in store.events]}, indent=2), encoding="utf-8"
    )


def record_from_benchmark(report: object, root: str | Path = ".") -> None:
    """Record events from a ComparativeReport."""
    for scenario in getattr(report, "scenarios", []):
        record_event(
            TelemetryEvent(
                timestamp=time.time(),
                task=getattr(scenario, "task", "")[:80],
                naive_tokens=getattr(scenario, "naive_tokens", 0),
                optimized_tokens=getattr(scenario, "optimized_tokens", 0),
                reduction_pct=getattr(scenario, "reduction_pct", 0.0),
                scenario=getattr(scenario, "scenario_id", ""),
            ),
            root=root,
        )

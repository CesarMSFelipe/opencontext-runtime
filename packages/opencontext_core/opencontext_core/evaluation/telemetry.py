"""Token savings telemetry — tracks cumulative token reduction over time."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

TELEMETRY_FILE = ".opencontext/telemetry.json"

# Canonical OC-OBS telemetry layout (mirrored to, in addition to the legacy
# single file kept for back-compat reads). Declared locally so this lower layer
# does not import the upper runtime_intelligence package (doc 58 dependency
# direction); the value matches
# ``runtime_intelligence.telemetry_layout.{TELEMETRY_DIR,EVENTS_FILE}``.
CANONICAL_TELEMETRY_DIR = ".opencontext/telemetry"
CANONICAL_EVENTS_FILE = "events.jsonl"

_NAIVE_TEXT_EXTS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".txt",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".php",
}
_NAIVE_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "build",
    ".storage",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "tmp",
    ".opencontext",
    ".mypy_cache",
    ".ruff_cache",
    "worktrees",
    "cache",
}


def estimate_naive_tokens(root: Path) -> int:
    """Rough token count an agent would read by ingesting the whole project.

    The honest "before" baseline: every source/text file's bytes (~4 chars/token),
    skipping vcs/build/vendored dirs. Shared by `pack`'s savings line and the
    `demo` so both report the same number. Returns at least 1.
    """
    chars = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _NAIVE_TEXT_EXTS:
            continue
        # Skip-dir check must be RELATIVE to root: an absolute prefix like /tmp
        # would otherwise match the "tmp" skip entry and drop the whole project.
        rel_parts = path.relative_to(root).parts
        if any(part in _NAIVE_SKIP_DIRS or part.endswith(".egg-info") for part in rel_parts):
            continue
        try:
            chars += path.stat().st_size
        except OSError:
            pass
    return max(chars // 4, 1)


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
    _mirror_to_canonical(event, root)


def _mirror_to_canonical(event: TelemetryEvent, root: str | Path = ".") -> None:
    """Also append the savings event to the canonical telemetry events ledger.

    Routes token-savings telemetry through the OC-OBS ``.opencontext/telemetry/``
    layout (append-only) while the legacy single file above stays readable. Best
    effort: a telemetry-write failure never breaks the caller.
    """
    try:
        events_dir = Path(root) / CANONICAL_TELEMETRY_DIR
        events_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": event.timestamp,
            "family": "runtime",
            "event": "telemetry.savings.recorded",
            "task": event.task,
            "naive_tokens": event.naive_tokens,
            "optimized_tokens": event.optimized_tokens,
            "reduction_pct": event.reduction_pct,
            "scenario": event.scenario,
        }
        with (events_dir / CANONICAL_EVENTS_FILE).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass


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

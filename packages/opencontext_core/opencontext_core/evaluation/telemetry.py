"""Token savings telemetry — tracks cumulative token reduction over time."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
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
    """Rough token count for ingesting the WHOLE project — a ceiling, not a headline.

    Sums every source/text file's bytes (~4 chars/token), skipping vcs/build/vendored
    dirs. This is the whole-repo *upper bound*: what an agent would read if it dumped
    the entire tree. It is NOT the honest per-task before baseline (no agent reads the
    whole repo for one task) — for a user-facing savings headline use
    :func:`estimate_included_files_tokens`, which counts only the files the pack drew
    from, whole (the same methodology as ``docs/benchmarks``). The internal evaluator
    (``evaluation/evaluator.py``) uses this deliberately as a labeled ceiling. Returns
    at least 1.
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


def estimate_included_files_tokens(root: Path, pack: object) -> int:
    """Honest per-task baseline: whole-file tokens of ONLY the files the pack drew from.

    This mirrors ``docs/benchmarks`` ("read the relevant files whole"): take the unique
    source files the pack included, and sum the cost of reading each one in full
    (~4 chars/token, the same heuristic used for the pack side of the display so both
    sides of the ratio use one estimator). Symbol pack items carry ``path:line`` or
    ``path:line:name`` sources; only the bare file path is used, and each file is
    counted once. Returns at least 1 so callers can divide safely.

    Unlike :func:`estimate_naive_tokens` (a whole-repo ceiling), this is the number a
    user-facing savings headline must use — no agent reads the entire repository to do
    one task, so comparing against the whole tree inflates the percentage by orders of
    magnitude.
    """
    root = Path(root)
    seen: set[Path] = set()
    chars = 0
    for item in getattr(pack, "included", []) or []:
        source = getattr(item, "source", "") or ""
        # graph items are "path:line" / "path:line:name"; file items are the bare path.
        raw = source.split(":", 1)[0]
        if not raw:
            continue
        candidate = Path(raw)
        path = candidate if candidate.is_absolute() else (root / candidate)
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if not resolved.is_file() or resolved.suffix not in _NAIVE_TEXT_EXTS:
            continue
        try:
            chars += resolved.stat().st_size
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


def _coerce_timestamp(value: object) -> float:
    """Best-effort coercion of a stored timestamp to a float epoch second."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _load_canonical(root: str | Path) -> list[TelemetryEvent]:
    """Read savings events from the canonical ``telemetry/events.jsonl`` ledger."""
    path = Path(root) / CANONICAL_TELEMETRY_DIR / CANONICAL_EVENTS_FILE
    if not path.exists():
        return []
    events: list[TelemetryEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("event") != "telemetry.savings.recorded":
            continue
        events.append(
            TelemetryEvent(
                timestamp=_coerce_timestamp(record.get("timestamp")),
                task=str(record.get("task", "")),
                naive_tokens=int(record.get("naive_tokens", 0) or 0),
                optimized_tokens=int(record.get("optimized_tokens", 0) or 0),
                reduction_pct=float(record.get("reduction_pct", 0.0) or 0.0),
                scenario=str(record.get("scenario", "")),
            )
        )
    return events


def _load_legacy(root: str | Path) -> list[TelemetryEvent]:
    """Read the pre-canonical single-file ``.opencontext/telemetry.json`` events."""
    path = Path(root) / TELEMETRY_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [TelemetryEvent(**e) for e in data.get("events", [])]
    except Exception:
        return []


def load_telemetry(root: str | Path = ".") -> TelemetryStore:
    """Load the cumulative token-savings store.

    Reads the canonical append-only ``.opencontext/telemetry/events.jsonl``;
    falls back to the legacy single-file ``.opencontext/telemetry.json`` only for
    projects written before the canonical layout, so old history is not orphaned.
    """
    events = _load_canonical(root)
    if not events:
        events = _load_legacy(root)
    return TelemetryStore(events=events)


def record_event(event: TelemetryEvent, root: str | Path = ".") -> None:
    """Append one savings event to the canonical telemetry ledger.

    Writes only ``.opencontext/telemetry/events.jsonl`` (append-only). The legacy
    whole-file ``.opencontext/telemetry.json`` is no longer written — it merely
    duplicated this ledger and inflated the project's artifact footprint.
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

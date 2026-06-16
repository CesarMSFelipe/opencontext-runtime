"""Honest retrieval evaluation: run the REAL retriever and measure what it found.

The comparative benchmark assumes perfect retrieval (it uses the hand-labeled
relevant files as the "optimized" set). This module instead runs the actual
context pack for each labeled task and measures:

* recall  — of the files a human marked relevant, how many did the pack include?
* precision — of the files the pack included, how many were relevant?
* token ratio — real pack tokens vs a realistic baseline (every source file in
  the directories the task touches — what a developer dumping the module would
  load), NOT the whole repository.
* latency — wall-clock to build the pack.

These are contrastable, reproducible numbers — no whole-repo vanity ratio.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

_SOURCE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".kt",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".php", ".swift", ".scala",
}


def _est_tokens(path: Path) -> int:
    try:
        return max(path.stat().st_size // 4, 0)
    except OSError:
        return 0


@dataclass(frozen=True)
class RecallTask:
    """A labeled task: a query plus the files a human says are needed for it."""

    id: str
    query: str
    relevant_files: list[str]  # repo-relative paths (ground truth)


@dataclass
class RecallResult:
    task_id: str
    recall: float
    precision: float
    pack_tokens: int
    baseline_tokens: int
    token_ratio: float  # pack / baseline (lower is better)
    latency_ms: float
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


@dataclass
class RecallReport:
    results: list[RecallResult]

    @property
    def median_recall(self) -> float:
        return median([r.recall for r in self.results]) if self.results else 0.0

    @property
    def mean_recall(self) -> float:
        return (sum(r.recall for r in self.results) / len(self.results)) if self.results else 0.0

    @property
    def zero_recall_tasks(self) -> int:
        """Tasks where the retriever found NONE of the relevant files (the misses)."""
        return sum(1 for r in self.results if r.recall == 0.0)

    @property
    def median_precision(self) -> float:
        return median([r.precision for r in self.results]) if self.results else 0.0

    @property
    def median_token_ratio(self) -> float:
        return median([r.token_ratio for r in self.results]) if self.results else 1.0

    def latency_p(self, pct: float) -> float:
        if not self.results:
            return 0.0
        ordered = sorted(r.latency_ms for r in self.results)
        idx = min(len(ordered) - 1, int(pct / 100 * len(ordered)))
        return ordered[idx]


def _pack_files(pack: Any, root: Path) -> set[str]:
    """Repo-relative files actually included in a context pack."""
    files: set[str] = set()
    for item in getattr(pack, "included", []):
        source = getattr(item, "source", "") or ""
        # graph items are "path:line:name"; file items are just the path.
        path = source.split(":", 1)[0]
        if not path:
            continue
        try:
            rel = str(Path(path).resolve().relative_to(root.resolve()))
        except ValueError:
            rel = path
        files.add(rel)
    return files


def _baseline_tokens(root: Path, relevant_files: list[str]) -> int:
    """Tokens of every source file in the directories the task's files live in.

    A realistic 'load the module' baseline — not the whole repository.
    """
    dirs = {(root / f).resolve().parent for f in relevant_files}
    seen: set[Path] = set()
    total = 0
    for d in dirs:
        if not d.is_dir():
            continue
        for p in d.iterdir():
            rp = p.resolve()
            if p.is_file() and p.suffix in _SOURCE_EXTS and rp not in seen:
                seen.add(rp)
                total += _est_tokens(p)
    return max(total, 1)


def run_recall_eval(runtime: Any, tasks: list[RecallTask], root: Path) -> RecallReport:
    """Run each task through the real retriever and measure recall/tokens/latency."""
    root = Path(root).resolve()
    results: list[RecallResult] = []
    for task in tasks:
        t0 = time.monotonic()
        pack = runtime.build_context_pack(task.query)
        latency_ms = (time.monotonic() - t0) * 1000

        included = _pack_files(pack, root)
        relevant = {f for f in task.relevant_files}
        hit = {f for f in relevant if any(inc == f or inc.endswith(f) for inc in included)}
        recall = len(hit) / len(relevant) if relevant else 1.0
        precision = (len(hit) / len(included)) if included else 0.0

        pack_tokens = int(getattr(pack, "used_tokens", 0) or 0)
        baseline = _baseline_tokens(root, task.relevant_files)
        results.append(
            RecallResult(
                task_id=task.id,
                recall=recall,
                precision=precision,
                pack_tokens=pack_tokens,
                baseline_tokens=baseline,
                token_ratio=pack_tokens / baseline,
                latency_ms=latency_ms,
                found=sorted(hit),
                missing=sorted(relevant - hit),
            )
        )
    return RecallReport(results=results)


def format_recall_report(report: RecallReport) -> str:
    """Human-readable summary with honest, per-task and aggregate numbers."""
    lines = ["Retrieval evaluation (real retriever vs labeled relevant files)", ""]
    for r in report.results:
        lines.append(
            f"  {r.task_id}: recall {r.recall:.0%}  precision {r.precision:.0%}  "
            f"pack {r.pack_tokens} tok ({r.token_ratio:.0%} of dir-baseline)  "
            f"{r.latency_ms:.0f} ms"
        )
        if r.missing:
            lines.append(f"      missed: {', '.join(r.missing)}")
    lines += [
        "",
        f"  mean recall        : {report.mean_recall:.0%}  "
        f"(median {report.median_recall:.0%}; "
        f"{report.zero_recall_tasks}/{len(report.results)} tasks found nothing)",
        f"  median precision   : {report.median_precision:.0%}",
        f"  median token ratio : {report.median_token_ratio:.0%} of the dir-baseline",
        f"  latency p50 / p95  : {report.latency_p(50):.0f} / {report.latency_p(95):.0f} ms",
    ]
    return "\n".join(lines)

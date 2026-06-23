"""REALISTIC-SIN arm — a careful OpenContext-free agent that reads WINDOWS, not files.

The headline SIN (:mod:`opencontext_core.evaluation.naive_agent`) reads every grep-hit
file in *full*. A more careful un-integrated agent does better: it greps the symbol,
then opens only a small window around each match (the lines it actually needs to see),
not the whole file. This module models that sharper control so the OC arms are
compared against the strongest realistic OpenContext-free baseline, not a strawman.

Honesty constraints:

* It imports NOTHING from ``opencontext_core.indexing`` / ``opencontext_core.runtime``
  / ``knowledge_graph``; file resolution is plain :mod:`re` over the working tree,
  identical to the SIN runner so token units are comparable across arms.
* ``tokens`` = Σ :func:`estimate_tokens` over a ~60-line window
  (``lines[max(0, hit-30):hit+30]``) around each matched line — the **same** estimator
  the product uses. Because each window is a strict subset of its file, this arm's
  token cost is by construction ≤ the full-file SIN cost.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.evaluation.models import ContextBenchCase
from opencontext_core.evaluation.multi_arm import ArmResult

# Mirror the SIN runner's file selection so the two controls iterate identically.
_SOURCE_EXTS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".kt",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".swift",
    ".scala",
}

_IGNORE_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "build",
    "dist",
    ".opencontext",
    ".storage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Half-window of lines read around each hit line (≈60-line window total).
_WINDOW_RADIUS = 30


def _is_ignored(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return any(part in _IGNORE_DIR_NAMES for part in rel.parts)


def _iter_source_files(root: Path) -> list[Path]:
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix in _SOURCE_EXTS and not _is_ignored(p, root)
    ]
    return sorted(files)


def _derive_target(case: ContextBenchCase) -> str:
    candidates: list[str] = _IDENT.findall(case.id.replace("-", " ").replace("/", " "))
    if not candidates:
        candidates = _IDENT.findall(case.query)
    if not candidates:
        return ""
    return max(candidates, key=len)


def run_realistic_case(case: ContextBenchCase, root: str | Path) -> ArmResult:
    """Measure a window-reading OpenContext-free control for one case.

    Procedure:
      1. Word-boundary regex-grep ``case.target_symbol`` (or a derived target) over the
         working tree — one grep pass, no subprocess.
      2. For each hit file, read only a ~60-line window
         (``lines[max(0, hit-30):hit+30]``) around each matched line and add
         :func:`estimate_tokens` of that window (overlapping windows in a file are
         merged so shared lines are counted once).
      3. ``tool_calls`` = 1 grep pass + one windowed read per hit file; ``latency_ms``
         is wall-clock.
    """
    root_path = Path(root).resolve()
    primary = case.target_symbol or _derive_target(case)

    t0 = time.monotonic()
    tokens = 0
    reads = 0

    if primary:
        pattern = re.compile(rf"\b{re.escape(primary)}\b")
        for path in _iter_source_files(root_path):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lines = text.splitlines()
            hit_indices = [i for i, line in enumerate(lines) if pattern.search(line)]
            if not hit_indices:
                continue
            # Merge per-hit windows so overlapping lines are counted once.
            wanted: set[int] = set()
            for idx in hit_indices:
                lo = max(0, idx - _WINDOW_RADIUS)
                hi = idx + _WINDOW_RADIUS
                wanted.update(range(lo, hi))
            window_text = "\n".join(lines[i] for i in sorted(wanted) if i < len(lines))
            tokens += estimate_tokens(window_text)
            reads += 1

    latency_ms = (time.monotonic() - t0) * 1000
    return ArmResult(
        arm="REALISTIC-SIN",
        tokens=tokens,
        tool_calls=1 + reads,
        latency_ms=latency_ms,
    )

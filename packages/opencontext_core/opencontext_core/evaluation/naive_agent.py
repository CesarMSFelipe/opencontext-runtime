"""SIN runner — a realistic, OpenContext-free control for the efficiency benchmark.

A real agent WITHOUT OpenContext, asked to "modify symbol X", does NOT have a
knowledge graph. It runs ``grep X`` across the working tree, sees which files and
references turn up, greps a few of those reference names too, then ``Read``s every
hit file in full to understand them. This module models exactly that loop and
returns the same :class:`CostTriple` shape as the CON side, so the per-case delta is
well-defined.

Honesty constraints (the whole point of this control):

* Files are resolved by **plain regex over the working tree** — this module imports
  NOTHING from ``opencontext_core.indexing`` / ``opencontext_core.runtime`` and never
  touches the ``KnowledgeGraph``. Using the system under test to power the control
  would understate the control's cost and overstate OpenContext's win.
* ``tokens``     = Σ :func:`estimate_tokens` over the full text of each hit file —
  the **same** estimator the product uses, so CON and SIN token units match.
* ``tool_calls`` = grep_passes + reads, counted directly (never derived).
* The caller-grep stage is **capped** (:data:`CALLER_GREP_CAP`) and file iteration is
  sorted, so the count is bounded and identical run-to-run.

This grows from the honest predecessor ``recall_eval.py`` (real-retriever + a
dir-baseline, not a whole-repo vanity ratio); it replaces "dump the directory" with
"grep + read only the hit files", which is a *harder*, more honest control.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.evaluation.models import ContextBenchCase, CostTriple

# Source extensions a real agent would actually open (mirrors recall_eval._SOURCE_EXTS).
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

# Directory fragments the indexer skips and a sane agent would never dump.
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

# Caller-grep cap (R2/DR1 — the honesty crux of the control).
#
# The brief's D-SIN-RESOLVE allows "one grep for the symbol + one per discovered caller
# name (capped top-5)". In practice, following arbitrary co-occurring identifiers makes
# the SIN balloon toward a WHOLE-REPO read (a single common method/type name like
# ``Path`` or ``write_text`` matches most of the tree), which is exactly the strawman
# the design forbids as the headline (R2). Measured on this repo, a top-5 caller follow
# pulled 99 to 2315 files for a single target.
#
# So the HEADLINE SIN models the realistic, bounded loop a careful un-integrated agent
# actually runs: grep the target symbol, then Read the files that reference it (those
# hit files already CONTAIN the call sites / callers). The caller follow-up is retained
# as a configurable, documented mechanism but defaults OFF (cap 0) so the control stays
# honest and reproducible rather than a repo crawl. Set >0 only to study a noisier agent.
CALLER_GREP_CAP = 0

# An identifier token used to derive a fallback target and scan matched lines.
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# A call site: an identifier immediately followed by "(" — what a developer chasing
# "who uses X" actually greps, as opposed to a substring of an import's dotted path.
_CALL_SITE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _is_ignored(path: Path, root: Path) -> bool:
    """True when any path segment (below root) is an ignored directory name."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return any(part in _IGNORE_DIR_NAMES for part in rel.parts)


def _iter_source_files(root: Path) -> list[Path]:
    """Deterministically-sorted source files under root, skipping ignored dirs."""
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix in _SOURCE_EXTS and not _is_ignored(p, root)
    ]
    return sorted(files)


def _grep(symbol: str, files: list[Path]) -> dict[Path, list[str]]:
    """Plain word-boundary regex search over already-listed files (one grep pass).

    Returns a mapping of hit file → the matched lines (used to harvest caller names).
    """
    if not symbol:
        return {}
    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    hits: dict[Path, list[str]] = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        matched = [line for line in text.splitlines() if pattern.search(line)]
        if matched:
            hits[path] = matched
    return hits


def _caller_names(matched_lines: list[str], primary: str) -> list[str]:
    """Distinctive caller/neighbour symbols a developer would chase next, by first sight.

    Models "the agent reads who references X and greps the *distinctive call sites* it
    sees" — NOT every word on the line. Two honesty rules keep this from degenerating
    into a whole-repo dump (R2/DR1):

    * ``import``/``from`` lines are skipped entirely — they yield module-path fragments
      (e.g. ``opencontext_core``, ``indexing``), which are not callers and would match
      most of the tree;
    * only **call sites** (``name(``) are harvested — actual invocations a developer
      would grep — excluding the primary itself and a few structural keywords.

    Capped by the caller at :data:`CALLER_GREP_CAP`.
    """
    skip = {
        primary,
        "def",
        "class",
        "return",
        "import",
        "from",
        "self",
        "super",
        "print",
        "len",
        "str",
        "int",
        "list",
        "dict",
        "set",
        "tuple",
        "isinstance",
        "range",
    }
    ordered: list[str] = []
    seen: set[str] = set()
    for line in matched_lines:
        stripped = line.lstrip()
        if stripped.startswith(("import ", "from ")):
            continue
        for token in _CALL_SITE.findall(line):
            if token in skip or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
    return ordered


def _derive_target(case: ContextBenchCase) -> str:
    """Fallback target symbol when a case declares none.

    Picks the longest identifier-like token from the case id, else from the query —
    a documented, deterministic heuristic for the 4 legacy cases that predate the
    ``target_symbol`` field.
    """
    candidates: list[str] = _IDENT.findall(case.id.replace("-", " ").replace("/", " "))
    if not candidates:
        candidates = _IDENT.findall(case.query)
    if not candidates:
        return ""
    return max(candidates, key=len)


def run_naive_case(
    case: ContextBenchCase,
    root: str | Path,
    *,
    caller_grep_cap: int = CALLER_GREP_CAP,
) -> CostTriple:
    """Measure the cost a realistic OpenContext-free agent pays for one case.

    Procedure (D-SIN-RESOLVE):
      1. grep the primary ``target_symbol`` over the working tree (1 grep pass);
      2. grep at most ``caller_grep_cap`` distinct caller names it surfaced
         (1 grep pass each) — defaults to :data:`CALLER_GREP_CAP` (0: the realistic,
         bounded headline control; see that constant for why following arbitrary
         callers degenerates into a whole-repo read);
      3. ``Read`` every distinct hit file in full, summing :func:`estimate_tokens`;
      4. ``tool_calls`` = grep_passes + reads; ``latency_ms`` = wall-clock.
    """
    root_path = Path(root).resolve()
    primary = case.target_symbol or _derive_target(case)

    t0 = time.monotonic()
    files = _iter_source_files(root_path)

    grep_passes = 0
    hit_files: dict[Path, None] = {}  # ordered set of distinct hit files

    # Stage 1: grep the primary symbol.
    primary_hits = _grep(primary, files)
    grep_passes += 1
    for path in primary_hits:
        hit_files.setdefault(path, None)

    # Stage 2 (optional): grep up to caller_grep_cap caller names surfaced by stage 1.
    all_matched: list[str] = []
    for lines in primary_hits.values():
        all_matched.extend(lines)
    for caller in _caller_names(all_matched, primary)[:caller_grep_cap]:
        caller_hits = _grep(caller, files)
        grep_passes += 1
        for path in caller_hits:
            hit_files.setdefault(path, None)

    # Stage 3: Read every distinct hit file in full.
    tokens = 0
    reads = 0
    for path in sorted(hit_files):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        tokens += estimate_tokens(text)
        reads += 1

    latency_ms = (time.monotonic() - t0) * 1000
    return CostTriple(
        tokens=tokens,
        tool_calls=grep_passes + reads,
        latency_ms=latency_ms,
    )

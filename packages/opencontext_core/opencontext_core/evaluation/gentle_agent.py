"""GENTLE-SIM arm — model a Gentle-AI-style "load the skill, then grep" loop.

Gentle-AI's documented apply loop loads a large prose SKILL file into context as
standing instructions, then — having no knowledge graph — falls back to grepping the
working tree for the symbol it must change and reading the hit files. This module
measures exactly that cost so it is comparable, in the SAME token unit, to the other
arms.

Honesty constraints (the point of this control):

* It imports NOTHING from ``opencontext_core.indexing`` / ``opencontext_core.runtime``
  / ``knowledge_graph`` — a Gentle-style agent has no such machinery, and powering the
  control with the system under test would understate its cost.
* File resolution is plain :mod:`re` over the working tree (``pathlib`` + ``re``, no
  ``subprocess``), mirroring :mod:`opencontext_core.evaluation.naive_agent` so token
  counts line up across arms.
* The standing-prompt cost (:data:`SKILL_FILE_TOKENS`) is sized from a *real* Gentle
  skill file when one can be located on disk (see :func:`_resolve_skill_tokens`), so
  the number is honest rather than invented; otherwise it falls back to a documented
  estimate.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from opencontext_core.context.budgeting import estimate_tokens
from opencontext_core.evaluation.models import ContextBenchCase
from opencontext_core.evaluation.multi_arm import ArmResult

# Source extensions and ignored-dir names mirror the SIN runner so the two controls
# iterate the working tree identically (token units stay comparable across arms).
_SOURCE_EXTS = {".py"}

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

# Candidate on-disk locations of a real Gentle/SDD apply SKILL file, in priority order.
# Sizing the standing-prompt cost from a real file keeps the control honest.
_SKILL_FILE_CANDIDATES: tuple[Path, ...] = (
    Path.home() / ".gentle-ai" / "skills" / "sdd-apply" / "SKILL.md",
    Path.home() / ".claude" / "skills" / "sdd-apply" / "SKILL.md",
    Path.home() / ".gentle-ai" / "SKILL.md",
)

# Documented fallback when no real skill file is found on disk: a Gentle apply-skill is
# a multi-page prose instruction file; ~800 tokens is a conservative documented
# estimate for such a standing prompt.
_DEFAULT_SKILL_FILE_TOKENS = 800


def _resolve_skill_tokens() -> tuple[int, str]:
    """Return ``(token_cost, source)`` for the Gentle standing-prompt.

    Prefers the token estimate of a REAL Gentle/SDD ``SKILL.md`` found at one of
    :data:`_SKILL_FILE_CANDIDATES`; ``source`` is then that file's path. When none is
    present, returns :data:`_DEFAULT_SKILL_FILE_TOKENS` with ``source="estimate"`` so
    the provenance of the number is always explicit.
    """
    for candidate in _SKILL_FILE_CANDIDATES:
        try:
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8", errors="ignore")
                return estimate_tokens(text), str(candidate)
        except OSError:
            continue
    return _DEFAULT_SKILL_FILE_TOKENS, "estimate"


# Resolved once at import. On this machine a real skill file is present at
# ~/.claude/skills/sdd-apply/SKILL.md, so SKILL_FILE_TOKENS is its honest
# estimate_tokens() value; otherwise it is the documented 800-token estimate above.
SKILL_FILE_TOKENS, SKILL_FILE_SOURCE = _resolve_skill_tokens()


def _is_ignored(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return any(part in _IGNORE_DIR_NAMES for part in rel.parts)


def _iter_source_files(root: Path) -> list[Path]:
    """Deterministically-sorted ``.py`` files under root, skipping ignored dirs."""
    files = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix in _SOURCE_EXTS and not _is_ignored(p, root)
    ]
    return sorted(files)


def _derive_target(case: ContextBenchCase) -> str:
    """Fallback target symbol — longest identifier in the id, else the query."""
    candidates: list[str] = _IDENT.findall(case.id.replace("-", " ").replace("/", " "))
    if not candidates:
        candidates = _IDENT.findall(case.query)
    if not candidates:
        return ""
    return max(candidates, key=len)


def run_gentle_case(
    case: ContextBenchCase,
    root: str | Path,
    *,
    top_k: int = 5,
) -> ArmResult:
    """Measure the cost of a Gentle-AI-style apply loop for one case.

    Procedure:
      1. Pay the standing-prompt cost :data:`SKILL_FILE_TOKENS` (the loaded skill).
      2. Word-boundary regex-grep ``case.target_symbol`` (or a derived target) over
         the ``.py`` files under ``root`` — one grep pass, no subprocess.
      3. Take the first ``top_k`` distinct hit files and add
         :func:`estimate_tokens` of each file's full text.
      4. ``tool_calls`` = 1 grep pass + one read per hit file; ``latency_ms`` is
         wall-clock.
    """
    root_path = Path(root).resolve()
    primary = case.target_symbol or _derive_target(case)

    t0 = time.monotonic()
    cost = SKILL_FILE_TOKENS

    hits: list[Path] = []
    if primary:
        pattern = re.compile(rf"\b{re.escape(primary)}\b")
        seen: set[Path] = set()
        for path in _iter_source_files(root_path):
            if len(hits) >= top_k:
                break
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if pattern.search(text) and path not in seen:
                seen.add(path)
                hits.append(path)

    for path in hits:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        cost += estimate_tokens(text)

    latency_ms = (time.monotonic() - t0) * 1000
    return ArmResult(
        arm="GENTLE-SIM",
        tokens=cost,
        tool_calls=1 + len(hits),
        latency_ms=latency_ms,
    )

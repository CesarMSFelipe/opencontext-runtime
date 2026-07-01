"""mem_current_project — thin wrapper over :func:`DetectProjectFull`.

REQ-OMT-007 / REQ-OMPD-001 — the eager surface ships
``mem_current_project(cwd=None) -> DetectionResult``. PR2.c.i shipped 3 of
the 5 cases inline; PR2.d refactors this module to be a pure delegation
shim so the full 5-case detector (``DetectProjectFull``) is the single
source of truth. Existing tests (T2.23) keep passing without modification
— the wrapper preserves the eager callable's name and zero-arg behavior.

Helpers that used to live here (``_slug_from_remote``, ``_read_remote_url``,
``_ancestor_git_repos``, ``_descendant_git_repos``) now live in
:mod:`opencontext_memory.project`. Re-exported here ONLY for backward
compatibility — callers that still import them via this module keep
working until PR4.d removes the shims.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_memory.project import (
    DetectionResult,
    DetectProjectFull,
    SourceLiteral,
    _ancestor_git_repos,
    _descendant_git_repos,
    _read_remote_url,
    _slug_from_remote,
    available_projects,
)


def mem_current_project(cwd: Path | None = None) -> DetectionResult:
    """Detect the project handle for ``cwd`` (defaults to ``Path.cwd()``).

    Thin wrapper around :func:`opencontext_memory.project.DetectProjectFull`.
    Same return shape; callers MUST inspect ``error`` before using
    ``project`` when ``source == "ambiguous"``.
    """
    resolved = Path(cwd).resolve() if cwd is not None else Path.cwd()
    return DetectProjectFull(resolved)


__all__ = [
    "DetectionResult",
    "SourceLiteral",
    "_ancestor_git_repos",
    "_descendant_git_repos",
    "_read_remote_url",
    "_slug_from_remote",
    "available_projects",
    "mem_current_project",
]

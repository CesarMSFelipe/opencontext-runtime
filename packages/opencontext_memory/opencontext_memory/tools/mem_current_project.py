"""mem_current_project — detect the project handle from the cwd.

REQ-OMT-007 — ``mem_current_project(*, recovery_token=None,
project_choice_reason=None) -> DetectionResult``.

The eager surface ships three of the five REQ-OMPD-001 cases:

1. ``git_remote`` — cwd inside a git repo whose ``origin`` URL parses to
   a clean slug (``OpenContext-Runtime`` etc.).
2. ``ambiguous`` — cwd sits below two or more git repos with no remote
   (the spec's "git_child ambiguous" path). The result carries
   ``error = "ambiguous_project"`` and ``available_projects`` so the
   surface caller can prompt the user.
3. ``dir_basename`` — no git context at all; fall back to the cwd name.

The full 5-case detector (``DetectProjectFull`` with config + git_remote
+ git_root + git_child + dir_basename + recovery_token flow) lands in
PR2.d. This module intentionally covers only what REQ-OMT-007 needs so
PR2.c.i ships without leaning on a project surface that doesn't exist
yet.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceLiteral = Literal[
    "config",
    "git_remote",
    "git_root",
    "git_child",
    "dir_basename",
    "user_selected",
    "ambiguous",
]


class DetectionResult(BaseModel):
    """The shape returned by :func:`mem_current_project`.

    Mirrors the spec's ``DetectionResult`` Pydantic model so future
    PR2.d work can re-use it. ``error`` is set ONLY when the result is
    ``ambiguous`` (the only failure mode this round).
    """

    model_config = ConfigDict(extra="forbid")

    project: str | None = Field(
        default=None, description="Detected project handle, or None on error."
    )
    source: SourceLiteral = Field(description="Which detection case fired.")
    path: str = Field(description="The cwd that produced this result.")
    warning: str | None = Field(default=None, description="Non-fatal warning text.")
    error: str | None = Field(default=None, description="Failure code (ambiguous_project).")
    available_projects: list[str] = Field(
        default_factory=list, description="Set only when error='ambiguous_project'."
    )
    recovery_token: str | None = Field(
        default=None, description="Token the caller re-presents when choosing."
    )


# Slug derivation per REQ-OMPD-004: split on ``:`` / ``/`` / ``.git``,
# lowercase, kebab-case. The expression also normalises the underscore
# form for the unusual SSH ``git@host:`` prefix.
_REMOTE_PARTS_RE = re.compile(r"[:/.]+")
_REMOTE_TRAILING_RE = re.compile(r"\.git$")


def _slug_from_remote(url: str) -> str | None:
    """Return a deterministic project slug for a git remote URL.

    Returns ``None`` when the URL yields no usable token. Both SSH
    (``git@github.com:foo/Bar.git``) and HTTPS
    (``https://github.com/foo/Bar.git``) forms resolve to ``bar``.
    """
    cleaned = _REMOTE_TRAILING_RE.sub("", url.strip())
    parts = [p for p in _REMOTE_PARTS_RE.split(cleaned) if p]
    if not parts:
        return None
    # SSH form prepends ``git@<host>``; the last two tokens are always
    # ``<owner>/<repo>`` for both schemes.
    slug = parts[-1].lower()
    slug = slug.replace("_", "-")
    return slug or None


def _read_remote_url(git_dir: Path) -> str | None:
    """Read the ``[remote "origin"] url =`` line from ``.git/config``.

    Pure-Python parser — no shelling out to the ``git`` CLI. The config
    format is INI-like and the line we need is unambiguous.
    """
    config_path = git_dir / "config"
    if not config_path.is_file():
        return None
    in_origin = False
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_origin = line == '[remote "origin"]'
            continue
        if not in_origin:
            continue
        if line.startswith("url") and "=" in line:
            return line.split("=", 1)[1].strip()
    return None


def _ancestor_git_repos(start: Path) -> list[Path]:
    """Return every ancestor git repo from ``start`` upward.

    Walks the parent chain (NOT into nested children — the spec's
    "two ancestor git repos" wording means two ancestors of the cwd).
    """
    repos: list[Path] = []
    seen: set[Path] = set()
    current = start.resolve()
    for candidate in (current, *current.parents):
        if candidate in seen:
            continue
        seen.add(candidate)
        git_dir = candidate / ".git"
        if git_dir.is_dir():
            repos.append(candidate)
    return repos


def _descendant_git_repos(start: Path) -> list[Path]:
    """Return git repos that exist as descendants of ``start`` (one level)."""
    repos: list[Path] = []
    seen: set[Path] = set()
    start = start.resolve()
    for entry in start.iterdir():
        if not entry.is_dir() or entry in seen:
            continue
        seen.add(entry)
        git_dir = entry / ".git"
        if git_dir.is_dir():
            repos.append(entry)
    return repos


def _git_repos_under(cwd: Path) -> list[Path]:
    """Combined ancestors + immediate descendants for the ambiguous check."""
    ancestors = _ancestor_git_repos(cwd)
    descendants = _descendant_git_repos(cwd)
    return [*ancestors, *descendants]


def mem_current_project(cwd: Path | None = None) -> DetectionResult:
    """Detect the project handle for ``cwd`` (defaults to ``Path.cwd()``).

    Returns a :class:`DetectionResult`; callers MUST inspect ``error``
    before using ``project`` when ``source == "ambiguous"``.
    """
    cwd = (cwd or Path.cwd()).resolve()
    ancestors = _ancestor_git_repos(cwd)
    descendants = _descendant_git_repos(cwd)

    # Case 1 — git_remote: cwd is inside an ancestor git repo with origin.
    # Iterate from closest-to-cwd upward; the closest wins.
    for repo in reversed(ancestors):
        remote = _read_remote_url(repo / ".git")
        if remote is None:
            continue
        slug = _slug_from_remote(remote)
        if slug is None:
            continue
        return DetectionResult(
            project=slug,
            source="git_remote",
            path=str(cwd),
        )

    # Case 2 — ambiguous: more than one ancestor git repo with no remote,
    # OR ancestors + descendants mixed with no remotes.
    remotes_less = [r for r in (*ancestors, *descendants) if _read_remote_url(r / ".git") is None]
    if len(remotes_less) >= 2:
        names = sorted({r.name for r in remotes_less})
        return DetectionResult(
            project=None,
            source="ambiguous",
            path=str(cwd),
            error="ambiguous_project",
            available_projects=names,
            recovery_token=None,
        )

    # Case 3 — git_root: exactly one ancestor git repo, no remote.
    if len(ancestors) == 1:
        return DetectionResult(
            project=ancestors[0].name,
            source="git_root",
            path=str(cwd),
        )

    # Case 4 — dir_basename fallback.
    return DetectionResult(
        project=cwd.name,
        source="dir_basename",
        path=str(cwd),
    )


__all__ = ["DetectionResult", "SourceLiteral", "mem_current_project"]

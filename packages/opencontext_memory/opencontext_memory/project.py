"""opencontext_memory.project — full 5-case project detection (REQ-OMPD-001…005).

Layered on top of :mod:`opencontext_memory.tools.mem_current_project` for
back-compat with the eager PR2.c.i surface. ``DetectProjectFull`` returns a
:class:`DetectionResult` carrying the project handle, the detection source,
the cwd's resolved path, an optional ``warning`` (the single-child
``git_child`` case), an optional ``error`` (only set to
``"ambiguous_project"`` when the host must pick), the list of
``available_projects`` and the one-shot ``recovery_token`` that closes the
ambiguous → user_selected loop.

The module also exposes the lightweight :func:`available_projects` helper
so downstream callers do not need to repeat the
``result.available_projects or []`` boilerplate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from secrets import token_hex
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
    """The shape returned by :func:`DetectProjectFull`.

    ``error`` is set ONLY when the result is ``ambiguous`` (the only failure
    mode the round-trip surfaces). ``warning`` is set ONLY when the result
    is ``git_child`` (single descendant git repo, auto-promoted).
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


# --- slug derivation (REQ-OMPD-004) -------------------------------------------

# Split on the canonical separators (``:`` / ``/`` / ``.git``). Both SSH
# (``git@github.com:foo/Bar.git``) and HTTPS
# (``https://github.com/foo/Bar.git``) forms resolve to ``bar`` because we
# only look at the last non-empty token.
_REMOTE_PARTS_RE = re.compile(r"[:/.]+")
_REMOTE_TRAILING_RE = re.compile(r"\.git$")


def _slug_from_remote(url: str) -> str | None:
    """Return a deterministic project slug for a git remote URL.

    Returns ``None`` when the URL yields no usable token. Both SSH and HTTPS
    forms resolve to the trailing repo name.
    """
    cleaned = _REMOTE_TRAILING_RE.sub("", url.strip())
    parts = [p for p in _REMOTE_PARTS_RE.split(cleaned) if p]
    if not parts:
        return None
    slug = parts[-1].lower().replace("_", "-")
    return slug or None


def _read_remote_url(git_dir: Path) -> str | None:
    """Read the ``[remote "origin"] url =`` line from ``.git/config``."""
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


# --- git repo discovery -------------------------------------------------------


def _ancestor_git_repos(start: Path) -> list[Path]:
    """Return every ancestor git repo from ``start`` upward."""
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


# --- config file resolution ---------------------------------------------------


def _read_config_project_name(cwd: Path) -> str | None:
    """Return ``project_name`` from ``.opencontext/config.json`` if present.

    Returns ``None`` when the file does not exist OR is malformed JSON.
    A malformed file is treated as "no config" so detection falls through
    to the git cases — never blocks the host.
    """
    config_path = cwd / ".opencontext" / "config.json"
    if not config_path.is_file():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("project_name")
    if not isinstance(name, str):
        return None
    name = name.strip()
    return name or None


# --- recovery-token bookkeeping ----------------------------------------------

_RECOVERY_TOKENS: dict[tuple[str, str], list[str]] = {}


def available_projects(result: DetectionResult) -> list[str]:
    """Defensive accessor for the ``available_projects`` field.

    Always returns a list (never ``None``) so callers do not need to repeat
    the ``result.available_projects or []`` boilerplate.
    """
    return list(result.available_projects)


# --- the 5-case detector ------------------------------------------------------


def DetectProjectFull(
    cwd: Path,
    *,
    recovery_token: str | None = None,
    selected_project: str | None = None,
    project_choice_reason: str | None = None,
) -> DetectionResult:
    """5-case project detector with recovery-token round-trip.

    Cases (in priority order, per REQ-OMPD-001):

    1. ``config``     — ``.opencontext/config.json`` carries ``project_name``
    2. ``git_remote`` — cwd sits inside a git repo whose ``origin`` URL parses
                        to a clean slug
    3. ``git_root``   — cwd sits inside a single git repo with no remote
    4. ``git_child``  — cwd is OUTSIDE any git ancestor but has exactly one
                        descendant git repo (auto-promote + warning)
    5. ``dir_basename`` — fallback to ``cwd.name``

    When 2+ ancestors or 2+ descendants all lack a remote, the result is
    ``source="ambiguous"`` with ``error="ambiguous_project"`` and a fresh
    ``recovery_token``; calling back with that token AND
    ``project_choice_reason="user_selected_after_ambiguous_project"`` AND
    ``selected_project=<name>`` resolves to ``source="user_selected"``.

    Any invalid token / wrong reason / non-listed selection raises
    ``ValueError("invalid_recovery_token")``.
    """
    cwd_resolved = Path(cwd).resolve()
    cwd_str = str(cwd_resolved)

    # ----- recovery-token path ---------------------------------------------
    if recovery_token is not None:
        key = (cwd_str, recovery_token)
        choices = _RECOVERY_TOKENS.get(key)
        if choices is None:
            raise ValueError("invalid_recovery_token")
        if project_choice_reason != "user_selected_after_ambiguous_project":
            raise ValueError("invalid_recovery_token")
        if selected_project is None or selected_project not in choices:
            raise ValueError("invalid_recovery_token")
        return DetectionResult(
            project=selected_project,
            source="user_selected",
            path=cwd_str,
            warning=None,
            error=None,
            available_projects=[],
            recovery_token=None,
        )

    # ----- 1. config case ---------------------------------------------------
    config_name = _read_config_project_name(cwd_resolved)
    if config_name:
        return DetectionResult(
            project=config_name,
            source="config",
            path=cwd_str,
            warning=None,
            error=None,
            available_projects=[],
            recovery_token=None,
        )

    # ----- 2/3/4. git cases -------------------------------------------------
    ancestors = _ancestor_git_repos(cwd_resolved)
    descendants = _descendant_git_repos(cwd_resolved)
    descendants_no_remote = [d for d in descendants if _read_remote_url(d / ".git") is None]

    # 2. ancestor with origin (closest wins — iterate from closest to farthest)
    for repo in reversed(ancestors):
        remote = _read_remote_url(repo / ".git")
        if remote is None:
            continue
        slug = _slug_from_remote(remote)
        if slug:
            return DetectionResult(
                project=slug,
                source="git_remote",
                path=cwd_str,
            )

    # 3/4/5. ambiguous (multi-ancestor), git_root (1 ancestor), or fall through
    ancestors_no_remote = [a for a in ancestors if _read_remote_url(a / ".git") is None]
    if len(ancestors_no_remote) >= 2:
        names = sorted({r.name for r in ancestors_no_remote})
        token = f"tok-{token_hex(8)}"
        _RECOVERY_TOKENS[(cwd_str, token)] = names
        return DetectionResult(
            project=None,
            source="ambiguous",
            path=cwd_str,
            error="ambiguous_project",
            available_projects=names,
            recovery_token=token,
        )

    if len(ancestors) == 1:
        return DetectionResult(
            project=ancestors[0].name,
            source="git_root",
            path=cwd_str,
        )

    # 4. single descendant → git_child
    if len(descendants_no_remote) == 1:
        child = descendants_no_remote[0]
        return DetectionResult(
            project=child.name,
            source="git_child",
            path=cwd_str,
            warning=f"auto_promoted_child:{child.name}:no_remote",
        )

    # 4b. multi-descendant ambiguous
    if len(descendants_no_remote) >= 2:
        names = sorted({d.name for d in descendants_no_remote})
        token = f"tok-{token_hex(8)}"
        _RECOVERY_TOKENS[(cwd_str, token)] = names
        return DetectionResult(
            project=None,
            source="ambiguous",
            path=cwd_str,
            error="ambiguous_project",
            available_projects=names,
            recovery_token=token,
        )

    # 5. dir_basename fallback
    return DetectionResult(
        project=cwd_resolved.name,
        source="dir_basename",
        path=cwd_str,
    )


__all__ = [
    "DetectProjectFull",
    "DetectionResult",
    "SourceLiteral",
    "available_projects",
]

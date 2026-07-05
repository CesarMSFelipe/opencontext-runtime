"""Strict-Path-only entry points for the paths resolver (amendment A4 audit).

The v2 design (commit 003 spec) tightens the contract: callers MUST pass
``pathlib.Path`` or get a ``TypeError`` raised. This module exports the
``*_strict`` aliases that delegate to the public
:func:`resolve_storage_path` / :func:`resolve_workspace_path` with
``strict_path=True`` — so migrations can verify the new shape one caller
at a time without modifying every call site.

Usage::

    from opencontext_core.paths.resolve_paths import resolve_storage_path_strict
    result = resolve_storage_path_strict(Path("/tmp/runtime"))  # OK
    resolve_storage_path_strict("/tmp/runtime")                  # raises TypeError
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.paths import (
    StorageMode,
)
from opencontext_core.paths import (
    resolve_storage_path as _resolve_storage_public,
)
from opencontext_core.paths import (
    resolve_workspace_path as _resolve_workspace_public,
)


def resolve_storage_path_strict(p: Path) -> Path:
    """Resolve the runtime storage directory from a strict-Path input.

    Delegates to :func:`resolve_storage_path` with ``strict_path=True``.
    Accepts ``pathlib.Path`` only; ``str`` raises ``TypeError``.
    """
    return _resolve_storage_public(p, StorageMode.local, custom=None, strict_path=True)


def resolve_workspace_path_strict(p: Path) -> Path:
    """Resolve the workspace directory from a strict-Path input."""
    return _resolve_workspace_public(p, StorageMode.local, custom=None, strict_path=True)


__all__ = [
    "resolve_storage_path_strict",
    "resolve_workspace_path_strict",
]

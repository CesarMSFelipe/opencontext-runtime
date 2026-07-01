"""Strict-Path-only entry points for the paths resolver.

The v1 `paths.resolve_storage_path(root, mode, custom)` accepts a `Path`
plus a `StorageMode` and an optional `str` override. The v2 design
spec (commit 003) tightens the contract: callers MUST pass `pathlib.Path`
or get a `TypeError` raised. This module re-exports the v1 helpers but
also enforces strict-Path handling at the `resolve_storage_path_strict`
boundary so migrations can verify the new shape one caller at a time.

Usage::

    from opencontext_core.paths.resolve_paths import resolve_storage_path_strict
    result = resolve_storage_path_strict(Path("/tmp/runtime"))  # OK
    resolve_storage_path_strict("/tmp/runtime")  # raises TypeError
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.paths import (
    StorageMode,
)
from opencontext_core.paths import (
    resolve_storage_path as _resolve_storage_v1,
)
from opencontext_core.paths import (
    resolve_workspace_path as _resolve_workspace_v1,
)


def _reject_str(name: str, value: object) -> None:
    """Raise TypeError if the caller passed a `str` instead of `Path`."""
    raise TypeError(
        f"{name} requires pathlib.Path; got str ({value!r}). "
        "Wrap with Path(...) at the call site."
    )


def _check_path(name: str, value: object) -> None:
    """Runtime check helper (mypy sees `Path`, runtime may see `str`)."""
    if not isinstance(value, Path) and isinstance(value, str):
        _reject_str(name, value)


def resolve_storage_path_strict(p: Path) -> Path:
    """Resolve the runtime storage directory from a `Path` input.

    Accepts ``pathlib.Path`` only. ``str`` raises ``TypeError``.
    """
    _check_path("resolve_storage_path_strict", p)
    return _resolve_storage_v1(p, StorageMode.local, custom=None)


def resolve_workspace_path_strict(p: Path) -> Path:
    """Resolve the workspace directory from a `Path` input."""
    _check_path("resolve_workspace_path_strict", p)
    return _resolve_workspace_v1(p, StorageMode.local, custom=None)


__all__ = [
    "resolve_storage_path_strict",
    "resolve_workspace_path_strict",
]

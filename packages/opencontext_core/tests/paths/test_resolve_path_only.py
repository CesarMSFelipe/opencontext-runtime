"""paths.resolve_* Path-only enforcement guard.

The v2 design (commit 003 spec) states: paths.resolve_storage_path
and paths.resolve_workspace_path SHALL accept `pathlib.Path` only;
legacy `str` callers SHALL raise TypeError to surface silent falls back
to the in-repo layout.

The existing v1 API is `(root: Path, mode: StorageMode, custom: str | None = None)`.
We add a NEW strict-Path resolver (call sites: paths/resolve_paths.py)
that delegates back to the v1 signature when fed Path inputs, and
raises TypeError on str inputs. This keeps the v1 surface working
while making migrations verifiable.

Wider migration of the ~160 f-string bypassers across context/cache/memory/
harness/runtime/sdk modules lands in commits 004 and 005.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.paths.resolve_paths import (
    resolve_storage_path_strict,
    resolve_workspace_path_strict,
)


def test_path_accepted_storage() -> None:
    """A `Path` argument is accepted and returns the resolved storage directory."""
    result = resolve_storage_path_strict(Path("/tmp/opencontext/test"))
    assert isinstance(result, Path)


def test_path_accepted_workspace() -> None:
    """A `Path` argument is accepted and returns the resolved workspace directory."""
    result = resolve_workspace_path_strict(Path("/tmp/opencontext/test"))
    assert isinstance(result, Path)


def test_str_rejected_storage() -> None:
    """A `str` argument is rejected with TypeError."""
    with pytest.raises(TypeError, match="Path"):
        resolve_storage_path_strict("/tmp/opencontext/test")  # type: ignore[arg-type]


def test_str_rejected_workspace() -> None:
    """A `str` argument is rejected with TypeError."""
    with pytest.raises(TypeError, match="Path"):
        resolve_workspace_path_strict("/tmp/opencontext/test")  # type: ignore[arg-type]

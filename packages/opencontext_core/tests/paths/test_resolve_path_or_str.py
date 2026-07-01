"""Public Path | str acceptance for paths.resolve_* (amendment A4).

Per amendment A4 ``paths.resolve_storage_path`` and
``paths.resolve_workspace_path`` accept ``pathlib.Path`` OR ``str`` as
their root argument publicly so CLI/MCP integrations do not break.
Passing ``str`` emits a ``DeprecationWarning`` (one-line hint to use
``Path(...)``); internal callers MAY opt into strict Path-only audit
mode by passing ``strict_path=True``.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _suppress_unrelated() -> None:
    """Each test inspects its own warning filter; nothing to set up."""
    return


def test_path_argument_accepted_without_warning() -> None:
    """A ``Path`` argument is accepted and returns the resolved directory.

    Confirms no ``DeprecationWarning`` is raised when the caller passes
    ``pathlib.Path``.
    """
    from opencontext_core.paths import (
        StorageMode,
        resolve_storage_path,
        resolve_workspace_path,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        storage = resolve_storage_path(Path("/tmp/opencontext-public-1"), StorageMode.local)
        workspace = resolve_workspace_path(
            Path("/tmp/opencontext-public-1"), StorageMode.local
        )
    assert isinstance(storage, Path)
    assert isinstance(workspace, Path)


def test_str_argument_accepted_with_deprecation_warning() -> None:
    """A ``str`` argument is accepted AND emits a ``DeprecationWarning``.

    The warning text hints at using ``pathlib.Path`` per the v2 contract.
    """
    from opencontext_core.paths import (
        StorageMode,
        resolve_storage_path,
        resolve_workspace_path,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        storage = resolve_storage_path(
            "/tmp/opencontext-public-2",  # type: ignore[arg-type]
            StorageMode.local,
        )
        workspace = resolve_workspace_path(
            "/tmp/opencontext-public-2",  # type: ignore[arg-type]
            StorageMode.local,
        )

    deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecation_warnings, "expected a DeprecationWarning on str input"
    assert any(
        "pathlib.Path" in str(w.message) for w in deprecation_warnings
    ), "warning text must hint at pathlib.Path"
    assert isinstance(storage, Path)
    assert isinstance(workspace, Path)


def test_strict_path_true_rejects_str() -> None:
    """``strict_path=True`` raises ``TypeError`` for non-Path inputs.

    Internal audit mode: the v2 cookie-cutter audits call sites using
    ``strict_path=True``; any remaining ``str`` caller is named in the
    audit report.
    """
    from opencontext_core.paths import (
        StorageMode,
        resolve_storage_path,
        resolve_workspace_path,
    )

    with pytest.raises(TypeError, match=r"pathlib\.Path"):
        resolve_storage_path(
            "/tmp/opencontext-strict",  # type: ignore[arg-type]
            StorageMode.local,
            strict_path=True,
        )
    with pytest.raises(TypeError, match=r"pathlib\.Path"):
        resolve_workspace_path(
            "/tmp/opencontext-strict",  # type: ignore[arg-type]
            StorageMode.local,
            strict_path=True,
        )


def test_strict_path_true_accepts_path() -> None:
    """``strict_path=True`` with ``Path`` input returns the resolved directory."""
    from opencontext_core.paths import (
        StorageMode,
        resolve_storage_path,
        resolve_workspace_path,
    )

    result_storage = resolve_storage_path(
        Path("/tmp/opencontext-strict-ok"),
        StorageMode.local,
        strict_path=True,
    )
    result_workspace = resolve_workspace_path(
        Path("/tmp/opencontext-strict-ok"),
        StorageMode.local,
        strict_path=True,
    )
    assert isinstance(result_storage, Path)
    assert isinstance(result_workspace, Path)

"""Central path resolver for OpenContext runtime state.

Provides a single source of truth for where generated state (KG, memory,
traces, embeddings) and workspace artifacts (harness, SDD, skills) live,
independent of the project repo.

Two modes
---------
* ``user`` (default): XDG / %LOCALAPPDATA% via platformdirs — keeps repo clean.
* ``local``: legacy in-repo ``.storage/opencontext`` / ``.opencontext`` layout
  (backward-compatible; selected by ``OPENCONTEXT_STORAGE_MODE=local`` env var).
"""

from __future__ import annotations

import hashlib
import json
import os
import warnings
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

import platformdirs

from opencontext_core.compat import StrEnum

__all__ = [
    "LegacyState",
    "StorageMode",
    "detect_legacy",
    "is_owned",
    "project_id",
    "read_manifest",
    "resolve_storage_path",
    "resolve_workspace_path",
    "write_manifest",
]

_MANIFEST_FILENAME = "oc-manifest.json"
_ENV_VAR = "OPENCONTEXT_STORAGE_MODE"


class StorageMode(StrEnum):
    """Storage location mode for runtime-generated state."""

    user = "user"
    local = "local"


def project_id(root: Path) -> str:
    """Return a 12-hex-char project identifier derived from the absolute root.

    Deterministic and collision-safe: ``sha256(str(root.resolve()))[:12]``.
    No files are created; no network calls are made.
    """
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]


def _effective_mode(mode: StorageMode) -> StorageMode:
    """Return the effective mode, honouring the OPENCONTEXT_STORAGE_MODE env var.

    ``OPENCONTEXT_STORAGE_MODE=local`` forces local (in-repo) storage.
    ``OPENCONTEXT_STORAGE_MODE=user`` forces user-mode (XDG) storage.
    Any other non-empty value emits a one-line warning and falls back to *mode*.
    """
    env_val = os.environ.get(_ENV_VAR, "").strip().lower()
    if env_val == StorageMode.local:
        return StorageMode.local
    if env_val == StorageMode.user:
        return StorageMode.user
    if env_val:
        warnings.warn(
            f"unknown {_ENV_VAR} value {env_val!r}; ignoring (valid: 'local', 'user')",
            stacklevel=3,
        )
    return mode


def resolve_storage_path(
    root: Path | str,
    mode: StorageMode,
    custom: str | None = None,
    *,
    strict_path: bool = False,
) -> Path:
    """Resolve the storage path for runtime-generated state.

    Per amendment A4 the public signature accepts ``Path | str`` so CLI/MCP
    integrations do not break. ``str`` inputs emit a ``DeprecationWarning``
    (one-line hint to use ``Path(...)``); internal callers opt into strict
    audit mode by passing ``strict_path=True``, which raises ``TypeError``
    when given a non-``Path`` value.

    Parameters
    ----------
    root:
        Absolute or relative project root; resolved to an absolute path internally.
        ``str`` is accepted for backward compatibility but emits a deprecation warning.
    mode:
        ``user`` → XDG/LOCALAPPDATA under the user home directory.
        ``local`` → ``<root>/.storage/opencontext`` (legacy layout).
    custom:
        If set, overrides both modes and returns ``Path(custom)`` directly.
    strict_path:
        When ``True``, ``root`` MUST be ``pathlib.Path``; otherwise ``TypeError``
        is raised. Default ``False``. Internal audit scripts pass ``True``.

    Environment override
    --------------------
    If ``OPENCONTEXT_STORAGE_MODE=local`` is set in the process environment,
    the resolver behaves as ``mode=local`` regardless of the *mode* argument.
    """
    if strict_path and not isinstance(root, Path):
        raise TypeError(
            f"resolve_storage_path requires pathlib.Path in strict_path mode; "
            f"got {type(root).__name__}. Wrap with Path(...) at the call site."
        )
    if isinstance(root, str):
        warnings.warn(
            "str paths are deprecated; pass pathlib.Path",
            DeprecationWarning,
            stacklevel=2,
        )
    root_path = Path(root)
    if custom:
        return Path(custom)
    effective = _effective_mode(mode)
    if effective == StorageMode.user:
        # Honor XDG_STATE_HOME cross-platform so tests + tooling get the
        # same XDG semantics on Linux, macOS and Windows. platformdirs
        # only honors XDG_STATE_HOME on POSIX; on Windows it falls back
        # to %LOCALAPPDATA% which breaks isolated test fixtures.
        xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
        if xdg_state:
            base = Path(xdg_state) / "opencontext"
        else:
            base = Path(platformdirs.user_state_path("opencontext"))
        return base / "projects" / project_id(root_path)
    # local mode — in-repo legacy layout
    return root_path.resolve() / ".storage" / "opencontext"


def resolve_workspace_path(
    root: Path | str,
    mode: StorageMode,
    custom: str | None = None,
    *,
    strict_path: bool = False,
) -> Path:
    """Resolve the workspace path for harness / SDD / skill artifacts.

    Per amendment A4 ``Path | str`` is accepted publicly; ``strict_path=True``
    switches to internal audit mode (see :func:`resolve_storage_path`).

    Parameters
    ----------
    root:
        Project root (resolved internally).
    mode:
        ``user`` → subdirectory under the resolved storage path.
        ``local`` → ``<root>/.opencontext`` (legacy workspace layout).
    custom:
        If set, the workspace is placed as ``<custom>/workspace``.
    strict_path:
        When ``True``, ``root`` MUST be ``pathlib.Path``; otherwise ``TypeError``.
    """
    if strict_path and not isinstance(root, Path):
        raise TypeError(
            f"resolve_workspace_path requires pathlib.Path in strict_path mode; "
            f"got {type(root).__name__}. Wrap with Path(...) at the call site."
        )
    if isinstance(root, str):
        warnings.warn(
            "str paths are deprecated; pass pathlib.Path",
            DeprecationWarning,
            stacklevel=2,
        )
    root_path = Path(root)
    effective = _effective_mode(mode)
    if effective == StorageMode.user:
        return resolve_storage_path(root_path, mode, custom) / "workspace"
    # local mode — in-repo legacy workspace
    return root_path.resolve() / ".opencontext"


@dataclass
class LegacyState:
    """Detected legacy in-repo state directories."""

    storage_path: Path | None
    """Path to ``.storage/opencontext`` if it exists under root, else None."""

    workspace_path: Path | None
    """Path to ``.opencontext`` if it exists under root, else None."""


def detect_legacy(root: Path) -> LegacyState | None:
    """Detect legacy in-repo state directories.

    Returns a :class:`LegacyState` if either ``.storage/opencontext`` or
    ``.opencontext`` exist under *root*, otherwise returns ``None``.

    This function never creates or deletes files.
    """
    abs_root = root.resolve()
    storage = abs_root / ".storage" / "opencontext"
    workspace = abs_root / ".opencontext"

    found_storage = storage if storage.exists() else None
    found_workspace = workspace if workspace.exists() else None

    if found_storage is None and found_workspace is None:
        return None

    return LegacyState(storage_path=found_storage, workspace_path=found_workspace)


def write_manifest(path: Path, root: Path, version: str) -> None:
    """Write an ownership manifest into *path*.

    The manifest file is named ``oc-manifest.json`` and contains:
    ``app``, ``project_root``, ``project_id``, ``created_by``, ``version``.

    Idempotent — safe to call on every runtime start; the file is overwritten
    with the current values so version is always up-to-date.
    """
    from datetime import datetime

    path.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "app": "opencontext",
        "project_root": str(root.resolve()),
        "project_id": project_id(root),
        "created_by": "runtime",
        "version": version,
        "created_at": datetime.now(tz=UTC).isoformat(),
    }
    manifest_file = path / _MANIFEST_FILENAME
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def read_manifest(path: Path) -> dict[str, Any] | None:
    """Read the ownership manifest from *path*.

    Returns the parsed dict if ``oc-manifest.json`` exists and is valid JSON,
    otherwise returns ``None``.
    """
    manifest_file = path / _MANIFEST_FILENAME
    if not manifest_file.exists():
        return None
    try:
        result: dict[str, Any] | None = json.loads(manifest_file.read_text(encoding="utf-8"))
        return result
    except (json.JSONDecodeError, OSError):
        return None


def is_owned(path: Path) -> bool:
    """Return ``True`` if *path* contains a manifest written by OpenContext.

    A path is considered owned when ``read_manifest(path)`` returns a dict with
    ``app == "opencontext"``.
    """
    manifest = read_manifest(path)
    return isinstance(manifest, dict) and manifest.get("app") == "opencontext"


# ---------------------------------------------------------------------------
# Internal helper used by detect_legacy callers to emit the standard warning
# ---------------------------------------------------------------------------


def _warn_legacy(legacy: LegacyState) -> None:
    """Emit a standard deprecation warning for detected legacy state."""
    paths = [str(p) for p in [legacy.storage_path, legacy.workspace_path] if p]
    path_str = " and ".join(paths)
    warnings.warn(
        f"legacy local state detected at {path_str}; "
        "run `opencontext storage migrate` to move it to the user directory",
        stacklevel=3,
    )

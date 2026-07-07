"""Mode-aware resolvers for execution-state roots (sessions, runs, checkpoints...).

Execution artifacts — sessions, runs, run bundles, checkpoints, receipts,
decision logs, learning state — must not accumulate inside project roots.
These helpers are the single source of truth for where that state lives:

* user mode (default): under the XDG project workspace
  (``$XDG_STATE_HOME/opencontext/projects/<hash>/workspace/...``)
* local mode (``OPENCONTEXT_STORAGE_MODE=local`` or ``storage.mode: local``):
  the legacy in-repo ``<root>/.opencontext/...`` layout, byte-identical to
  the pre-migration behaviour.

Writers call the ``*_root`` resolvers; dir-scanning readers use
:func:`execution_read_roots` (active-first, legacy in-repo fallback) and
file readers use ``config_resolver.resolve_active_workspace_file``.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "checkpoints_root",
    "execution_read_roots",
    "execution_workspace",
    "learning_root",
    "receipts_root",
    "runs_root",
    "sessions_root",
]


def execution_workspace(root: Path | str) -> Path:
    """The active (config/env-driven) workspace all execution state hangs off.

    A malformed / unreadable ``opencontext.yaml`` must never crash path
    resolution — the run layer reports ``needs_configuration`` separately and
    still has to persist that evidence somewhere. On config-load failure the
    resolver falls back to the built-in default mode (``user``); the
    ``OPENCONTEXT_STORAGE_MODE`` env override still applies inside
    :func:`opencontext_core.paths.resolve_workspace_path`.
    """
    # Imported lazily: config_resolver imports this package at module scope.
    from opencontext_core.config_resolver import resolve_active_workspace_path

    root_path = Path(root)
    try:
        return resolve_active_workspace_path(root_path)
    except Exception:
        from opencontext_core.paths import StorageMode, resolve_workspace_path

        return resolve_workspace_path(root_path, StorageMode.user)


def sessions_root(root: Path | str) -> Path:
    """``<workspace>/sessions`` — durable session/run trees."""
    return execution_workspace(root) / "sessions"


def runs_root(root: Path | str) -> Path:
    """``<workspace>/runs`` — flat per-run artifact dirs + run index."""
    return execution_workspace(root) / "runs"


def checkpoints_root(root: Path | str) -> Path:
    """``<workspace>/checkpoints`` — reversible file checkpoints."""
    return execution_workspace(root) / "checkpoints"


def receipts_root(root: Path | str) -> Path:
    """``<workspace>/receipts`` — run/provider receipt ledgers."""
    return execution_workspace(root) / "receipts"


def learning_root(root: Path | str) -> Path:
    """``<workspace>/learning`` — decision logs, candidates, evolution state."""
    return execution_workspace(root) / "learning"


def execution_read_roots(root: Path | str, name: str) -> list[Path]:
    """Candidate dirs for *name*, active location first, legacy in-repo second.

    Dir-scanning readers (runs/sessions listings) iterate these so runs
    persisted before the user-mode migration stay visible. In local mode both
    candidates coincide and the list collapses to one entry. Never creates
    directories.
    """
    from opencontext_core.paths import StorageMode, resolve_workspace_path

    root_path = Path(root)
    active = execution_workspace(root_path) / name
    legacy = resolve_workspace_path(root_path, StorageMode.local) / name
    if active == legacy:
        return [active]
    return [active, legacy]

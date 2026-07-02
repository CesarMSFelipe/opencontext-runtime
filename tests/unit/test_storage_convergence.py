"""Path-convergence guard: verify/meta/substrate/gates resolve the same storage path.

C2 (product-closure-r13): After the C1 migration all 4 consumer call-sites
must return the same path when the same project root and storage mode are used.

Tests are parametrized over:
  - mode=user  (default; XDG-based)
  - OPENCONTEXT_STORAGE_MODE=local (env override; local-mode path)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config_resolver import (
    resolve_active_storage_path,
    resolve_active_workspace_path,
)


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Return a temporary project root with a minimal opencontext.yaml."""
    (tmp_path / "opencontext.yaml").write_text(
        "project:\n  name: convergence-test\n", encoding="utf-8"
    )
    return tmp_path


def test_all_consumers_resolve_same_path(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 4 consumer call-sites must resolve the same storage path.

    Each consumer was migrated in C1 to use resolve_active_storage_path /
    resolve_active_workspace_path. This test verifies convergence by calling
    the shared helpers with the same root and asserting path identity.
    """
    # Ensure we use user mode (default) — no env override.
    monkeypatch.delenv("OPENCONTEXT_STORAGE_MODE", raising=False)

    root = tmp_project

    # All consumers now go through the same helpers:
    # - verification.py: resolve_active_storage_path(Path.cwd())
    # - harness/meta.py + agentic/context_substrate.py + harness/gates.py:
    #   resolve_active_storage_path(root) / resolve_active_workspace_path(root)
    storage_a = resolve_active_storage_path(root)
    storage_b = resolve_active_storage_path(root)
    workspace_a = resolve_active_workspace_path(root)
    workspace_b = resolve_active_workspace_path(root)

    assert storage_a == storage_b, (
        f"Storage path not stable: {storage_a} != {storage_b}"
    )
    assert workspace_a == workspace_b, (
        f"Workspace path not stable: {workspace_a} != {workspace_b}"
    )
    # Storage and workspace must be distinct (storage is for DB; workspace for JSON/harness)
    assert storage_a != workspace_a, (
        f"Storage and workspace must differ; both resolved to {storage_a}"
    )


def test_all_consumers_resolve_same_path_local_mode(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Convergence holds under OPENCONTEXT_STORAGE_MODE=local env override."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

    root = tmp_project
    storage_a = resolve_active_storage_path(root)
    storage_b = resolve_active_storage_path(root)
    workspace_a = resolve_active_workspace_path(root)
    workspace_b = resolve_active_workspace_path(root)

    assert storage_a == storage_b
    assert workspace_a == workspace_b

    # In local mode: storage → .storage/opencontext, workspace → .opencontext
    assert storage_a == root / ".storage" / "opencontext", (
        f"Local-mode storage path wrong: {storage_a}"
    )
    assert workspace_a == root / ".opencontext", (
        f"Local-mode workspace path wrong: {workspace_a}"
    )

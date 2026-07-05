"""F6: opencontext storage migrate moves legacy in-repo state to XDG user dir.

Tests verify:
- The 'storage migrate' subcommand exists and is reachable.
- It moves legacy .storage/opencontext + .opencontext dirs to the user XDG path.
- It is idempotent (second run is a no-op, exits 0).
- --dry-run prints moves without performing them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect XDG_STATE_HOME so migrate never writes to the real user dir."""
    xdg = tmp_path / "xdg_state"
    xdg.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(xdg))


def _run_storage_migrate(
    project: Path, *, dry_run: bool = False
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "opencontext_cli.main", "storage", "migrate", str(project)]
    if dry_run:
        cmd.append("--dry-run")
    return subprocess.run(cmd, capture_output=True, text=True)


def test_storage_migrate_subcommand_exists(tmp_path: Path) -> None:
    """'opencontext storage migrate' must be a recognized command (exits 0, not 'unknown')."""
    result = _run_storage_migrate(tmp_path)
    assert "unknown" not in result.stderr.lower(), (
        f"storage migrate not recognized: stderr={result.stderr!r}"
    )
    assert result.returncode == 0


def test_storage_migrate_moves_legacy_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy .storage/opencontext is moved to the user XDG path after migrate."""
    legacy = tmp_path / ".storage" / "opencontext"
    legacy.mkdir(parents=True)
    (legacy / "context_graph.db").write_bytes(b"fake-db")

    result = _run_storage_migrate(tmp_path)
    assert result.returncode == 0, f"migrate failed: {result.stderr}"
    # Legacy path must be gone (or empty)
    assert not legacy.exists() or not (legacy / "context_graph.db").exists(), (
        "legacy storage not moved"
    )


def test_storage_migrate_is_idempotent(tmp_path: Path) -> None:
    """Running storage migrate twice must succeed both times (idempotent)."""
    legacy = tmp_path / ".storage" / "opencontext"
    legacy.mkdir(parents=True)
    (legacy / "data.txt").write_text("x", encoding="utf-8")

    result1 = _run_storage_migrate(tmp_path)
    result2 = _run_storage_migrate(tmp_path)

    assert result1.returncode == 0, f"first migrate failed: {result1.stderr}"
    assert result2.returncode == 0, f"second migrate failed: {result2.stderr}"


def test_storage_migrate_dry_run_does_not_move(tmp_path: Path) -> None:
    """--dry-run prints what would be moved but leaves legacy dirs in place."""
    legacy = tmp_path / ".storage" / "opencontext"
    legacy.mkdir(parents=True)
    (legacy / "context_graph.db").write_bytes(b"fake-db")

    result = _run_storage_migrate(tmp_path, dry_run=True)
    assert result.returncode == 0, f"dry-run failed: {result.stderr}"
    # The file must still be there (dry-run must not actually move it)
    assert (legacy / "context_graph.db").exists(), "dry-run moved the file (it must not)"
    # Output must mention the move
    combined = result.stdout + result.stderr
    assert "dry" in combined.lower() or "would" in combined.lower(), (
        f"dry-run did not indicate preview mode: {combined!r}"
    )


def test_storage_migrate_no_legacy_is_noop(tmp_path: Path) -> None:
    """When there is no legacy state, migrate exits 0 and reports nothing to do."""
    result = _run_storage_migrate(tmp_path)
    assert result.returncode == 0, f"migrate with no legacy failed: {result.stderr}"
    lowered = (result.stdout + result.stderr).lower()
    assert "nothing" in lowered or "no legacy" in lowered or "already" in lowered, (
        f"expected 'nothing to do' message; got: {lowered!r}"
    )

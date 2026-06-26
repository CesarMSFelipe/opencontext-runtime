"""REQ-03b: MetaHarnessScanner behavioral tests.

(a) Empty temp dir → passed=False (score < 90).
(b) Actual repo CWD → passed=True (skip if KG absent).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.harness.meta import MetaHarnessScanner


def test_empty_dir_scores_below_gate(tmp_path: Path) -> None:
    """An empty directory must score below the pass gate (< 90)."""
    scanner = MetaHarnessScanner(root=tmp_path)
    report = scanner.scan()

    assert report.passed is False, (
        f"Expected empty dir to fail (score < 90), but got score={report.score}. "
        f"Passing checks: {[c.name for c in report.checks if c.passed]}"
    )
    assert report.score < 90

    # At least one check should have a failure reason.
    failing = [c for c in report.checks if not c.passed]
    assert len(failing) >= 1, "Expected at least one failing check in an empty directory"


def test_empty_dir_mcp_json_check_fails(tmp_path: Path) -> None:
    """The mcp_json check must fail in an empty directory."""
    scanner = MetaHarnessScanner(root=tmp_path)
    report = scanner.scan()

    mcp_check = next(c for c in report.checks if c.name == "mcp_json")
    assert mcp_check.passed is False


def test_empty_dir_opencontext_yaml_check_fails(tmp_path: Path) -> None:
    """The opencontext_yaml check must fail in an empty directory."""
    scanner = MetaHarnessScanner(root=tmp_path)
    report = scanner.scan()

    yaml_check = next(c for c in report.checks if c.name == "opencontext_yaml")
    assert yaml_check.passed is False


def test_empty_dir_delegates_check_fails(tmp_path: Path) -> None:
    """The hidden_delegates_path check must fail in an empty directory."""
    scanner = MetaHarnessScanner(root=tmp_path)
    report = scanner.scan()

    delegates_check = next(c for c in report.checks if c.name == "hidden_delegates_path")
    assert delegates_check.passed is False


def test_repo_cwd_passes_when_kg_present() -> None:
    """The actual repo CWD must score >= 90 when KG is populated (skip if absent)."""
    import sqlite3

    repo_root = Path(__file__).parents[2]  # tests/ parent = repo root
    db_path = repo_root / ".storage" / "opencontext" / "context_graph.db"

    if not db_path.exists():
        pytest.skip("KG database not present — skipping repo health check")

    # Verify the KG has at least some nodes.
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        finally:
            conn.close()
    except Exception:
        pytest.skip("KG database unreadable — skipping repo health check")

    if count == 0:
        pytest.skip("KG database is empty — skipping repo health check")

    scanner = MetaHarnessScanner(root=repo_root)
    report = scanner.scan()

    assert report.passed is True, (
        f"Expected repo root to pass (score >= 90), but got score={report.score}. "
        f"Failing checks: {[(c.name, c.explanation) for c in report.checks if not c.passed]}"
    )

"""Phase-0 release blocker guards: pytest collection must succeed cleanly.

Three properties must hold before any v2 commit lands:
1. `python -m pytest packages/opencontext_core/tests -q --co` collects > 0 tests
   with zero collection errors (no missing __init__.py, no module-name
   collisions).
2. Every test directory that holds subpackage tests exposes an
   __init__.py so pytest treats it as a single package and avoids the
   "imported module X has this __file__ attribute" cross-import shadow.
3. No two test files share the same basename across distinct test
   packages (e.g. test_metrics.py in onboarding/ vs cache/v2/).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parents[1]  # packages/opencontext_core/tests


def _has_subpackage_tests(p: Path) -> bool:
    """True if *p* contains a sub-package directory holding test_*.py files."""
    return any(
        (child.is_dir() and not child.name.startswith("_") and not child.name.startswith("."))
        and any(child.glob("test_*.py"))
        for child in p.iterdir()
    )


@pytest.mark.parametrize(
    "subdir",
    [
        "memory",
        "memory/v2",
        "cache",
        "cache/v2",
        "context",
        "context/v2",
        "plugins",
        "plugins/v2",
        "marketplace",
        "marketplace/v2",
        "providers",
        "providers/v2",
        "benchmarks",
        "benchmarks/v2",
        "studio",
        "studio/v2",
        "onboarding",
    ],
)
def test_v2_init_files_present(subdir: str) -> None:
    """Every package holding test_*.py files MUST export __init__.py."""
    target = TESTS_ROOT / subdir
    assert target.is_dir(), f"required test directory missing: {subdir}"
    assert (target / "__init__.py").is_file(), (
        f"missing __init__.py for {subdir}; pytest treats it as a "
        "namespace package and cross-imports collide between sibling dirs."
    )


def test_no_duplicate_test_module_names() -> None:
    """No two packages may hold a test_*.py with the same basename."""
    seen: dict[str, list[str]] = {}
    for test_file in TESTS_ROOT.rglob("test_*.py"):
        if "__pycache__" in test_file.parts:
            continue
        seen.setdefault(test_file.name, []).append(str(test_file.relative_to(TESTS_ROOT)))
    duplicates = {name: paths for name, paths in seen.items() if len(paths) > 1}
    assert not duplicates, f"Duplicate test module basenames (rename one set): {duplicates}"


def test_pytest_collects_zero_errors() -> None:
    """`pytest --collect-only -q` exits 0 with zero collection errors."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS_ROOT), "-q", "--co", "--no-header"],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"pytest collect failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "error" not in result.stderr.lower(), f"pytest collect reported errors:\n{result.stderr}"

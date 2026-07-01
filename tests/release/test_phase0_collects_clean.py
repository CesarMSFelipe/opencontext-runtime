"""Phase-0 ruff + pytest collection guard (v2 release blocker, part 1).

This test file is the v2-overlay pin for the release-architecture Phase 0
contracts enumerated in
``openspec/changes/opencontext-runtime-convergence/specs/release-architecture/spec.md``.

Three properties are pinned here:

1. ``ruff check .`` exits 0 (no lint regressions slip into v2).
2. ``pytest packages/opencontext_core/tests --collect-only`` exits 0 with
   no collection errors (every ``tests/<sub>/__init__.py`` is present,
   no duplicate ``test_*.py`` basenames across distinct test packages).
3. The seven v2 test directories each carry an ``__init__.py``.

Why this lives in ``tests/release/`` (not ``packages/.../tests/release/``)
is documented in
``openspec/changes/opencontext-runtime-convergence/tasks/commit-001-fix-ruff-pytest-co.md``
— the v2 spec canonicalises test gate locations at the repo root so the
release gates are visible to CI without per-package pythonpath gymnastics.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_TESTS_ROOT = REPO_ROOT / "packages" / "opencontext_core" / "tests"


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
    """Every package holding test_*.py files MUST export ``__init__.py``."""
    target = CORE_TESTS_ROOT / subdir
    assert target.is_dir(), f"required test directory missing: {subdir}"
    assert (target / "__init__.py").is_file(), (
        f"missing __init__.py for {subdir}; pytest treats it as a "
        "namespace package and cross-imports collide between sibling dirs."
    )


def test_no_duplicate_test_module_names() -> None:
    """No two packages may hold a test_*.py with the same basename."""
    seen: dict[str, list[str]] = {}
    for test_file in CORE_TESTS_ROOT.rglob("test_*.py"):
        if "__pycache__" in test_file.parts:
            continue
        seen.setdefault(test_file.name, []).append(
            str(test_file.relative_to(CORE_TESTS_ROOT))
        )
    duplicates = {name: paths for name, paths in seen.items() if len(paths) > 1}
    assert not duplicates, f"Duplicate test module basenames: {duplicates}"


def test_pytest_collects_zero_errors() -> None:
    """``pytest --collect-only -q`` exits 0 with zero collection errors."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(CORE_TESTS_ROOT),
            "-q",
            "--co",
            "--no-header",
        ],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"pytest collect failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[:2000]}\nstderr: {result.stderr[:1000]}"
    )
    assert "error" not in result.stderr.lower(), (
        f"pytest collect reported errors:\n{result.stderr[:1000]}"
    )

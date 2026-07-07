"""Inspection verification commands must not litter the project tree.

The external checks (lint/typecheck/targeted tests) run INSIDE the user's
project. PRODUCT_CONTRACT §Storage modes / AC-031: executions leave no
artifacts in the project — so the child environment must suppress Python
bytecode caches (``PYTHONDONTWRITEBYTECODE``) and pytest's on-disk cache
(``PYTEST_ADDOPTS='-p no:cacheprovider'``).
"""

from __future__ import annotations

import sys
from pathlib import Path

from opencontext_core.oc_flow.inspection import run_local_inspection

_ENV_PROBE = (
    "import os, sys; "
    "ok = os.environ.get('PYTHONDONTWRITEBYTECODE') == '1' "
    "and 'no:cacheprovider' in os.environ.get('PYTEST_ADDOPTS', ''); "
    "sys.exit(0 if ok else 1)"
)


def test_targeted_tests_run_with_cache_suppressing_env(tmp_path: Path) -> None:
    """The test command's env forbids __pycache__ and .pytest_cache residue."""
    report = run_local_inspection(
        tmp_path,
        [],
        test_command=[sys.executable, "-c", _ENV_PROBE],
        run_external=True,
    )
    gate = next(g for g in report.gate_results if g["id"] == "targeted_tests")
    assert gate["exit_code"] == 0, (
        "AC-031: the verification env must set PYTHONDONTWRITEBYTECODE=1 and "
        "PYTEST_ADDOPTS='-p no:cacheprovider' so project trees stay clean"
    )
    assert report.verification_outcome == "passed"


def test_verification_env_does_not_leak_outer_pytest_vars(tmp_path: Path, monkeypatch) -> None:
    """Outer PYTEST_* vars are stripped so nested runs are not misconfigured."""
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw9")
    probe = "import os, sys; sys.exit(1 if 'PYTEST_XDIST_WORKER' in os.environ else 0)"
    report = run_local_inspection(
        tmp_path,
        [],
        test_command=[sys.executable, "-c", probe],
        run_external=True,
    )
    gate = next(g for g in report.gate_results if g["id"] == "targeted_tests")
    assert gate["exit_code"] == 0, "outer PYTEST_* env vars must not leak into verification"


def test_tdd_evidence_capture_suppresses_pytest_cache(tmp_path: Path) -> None:
    """RED/GREEN evidence runs must not write .pytest_cache into the project."""
    from opencontext_core.tdd.red_green import capture_test_run

    evidence = capture_test_run([sys.executable, "-c", _ENV_PROBE], tmp_path)
    assert evidence.exit_code == 0, (
        "AC-031: capture_test_run must set PYTHONDONTWRITEBYTECODE=1 and "
        "PYTEST_ADDOPTS='-p no:cacheprovider' so evidence runs leave no residue"
    )

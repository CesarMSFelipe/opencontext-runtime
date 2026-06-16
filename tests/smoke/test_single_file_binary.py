"""The single-file build produces a runnable executable.

Builds dist into a tmp path and runs the artifact as a subprocess, so this is a
real end-to-end proof of the distribution path — not a check that the source
imports.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
_BUILD_SCRIPT = ROOT / "scripts" / "build_binary.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_binary", _BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_pyz_builds_and_runs(tmp_path: Path) -> None:
    out = tmp_path / "opencontext.pyz"
    built = _load_builder().build(out)
    assert built.exists() and built.stat().st_size > 0

    # The artifact runs as a standalone file and reports a version.
    result = subprocess.run(
        [sys.executable, str(built), "--version"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "opencontext" in (result.stdout + result.stderr).lower()


def test_pyz_runs_a_real_command(tmp_path: Path) -> None:
    out = tmp_path / "opencontext.pyz"
    built = _load_builder().build(out)

    result = subprocess.run(
        [sys.executable, str(built), "contract", "build", "--query", "fix auth bug"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "risk_tier:" in result.stdout  # the bundled CLI actually executed

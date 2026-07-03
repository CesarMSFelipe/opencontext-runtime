"""A2 — OC Flow bugfix: seeded project, test_stub provider, CLI run fixes the bug.

Recipe (§6.2 of runtime13-review.md):
1. Build a seeded tmp project containing:
   - ``calc.py``:  buggy implementation (``a - b`` instead of ``a + b``)
   - ``test_calc.py``: pytest that asserts ``add(2, 3) == 5`` (fails before fix)
   - ``opencontext.yaml``:  ``provider: test_stub`` + ``edits_file: edits.json``
   - ``edits.json``: ApplyEdit set that replaces the buggy line with the fix
2. Run ``./.venv/bin/opencontext run "Fix failing test"`` via subprocess with
   isolated HOME (no real credentials, no ~/.opencontext pollution) and
   ``OPENCONTEXT_STORAGE_MODE=local`` so storage stays in the tmp dir.
3. Verify the run exits 0 (or status=="completed" via JSON).
4. Run ``pytest test_calc.py`` in the tmp dir; success means the fix was applied.

Exit-code translation is honest:
- pytest exit 0 → success=True
- pytest exit !=0 → success=False, detail=last stdout/stderr line
- subprocess timeout → success=False, detail="timeout after Ns"
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from opencontext_core.benchmarks.v2.methodology import current_methodology_version
from opencontext_core.benchmarks.v2.runner import BenchmarkResult

SUITE_ID = "A2"
_REPO_ROOT = Path(__file__).resolve().parents[6]
_CLI = str(_REPO_ROOT / ".venv" / "bin" / "opencontext")
_TIMEOUT_RUN = 120  # opencontext run
_TIMEOUT_TEST = 60  # pytest verify

_BUGGY_CALC = """\
def add(a, b):
    return a - b
"""

_TEST_CALC = """\
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from calc import add

def test_add_returns_sum():
    assert add(2, 3) == 5
"""

# ApplyEdit set that replaces the buggy operator on line 2.
_EDITS_JSON = json.dumps(
    [
        {
            "path": "calc.py",
            "operation": "replace_range",
            "start_line": 2,
            "end_line": 2,
            "content": "    return a + b\n",
            "reason": "fix subtraction operator to addition",
            "requirement_refs": ["add returns the sum of a and b"],
        }
    ]
)

_OC_YAML = "provider: test_stub\nedits_file: edits.json\n"


def _isolated_env(home: str) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = home
    env["OPENCONTEXT_STORAGE_MODE"] = "local"
    # Clear any real provider credentials so test_stub path is taken.
    for key in list(env):
        if key.startswith("OPENAI_") or key.startswith("ANTHROPIC_") or key.startswith("GEMINI_"):
            env.pop(key, None)
    return env


def run() -> BenchmarkResult:
    """Seed a buggy project, run opencontext fix via CLI, verify pytest passes."""
    with tempfile.TemporaryDirectory(prefix="oc_bench_a2_") as tmpdir_s:
        tmpdir = Path(tmpdir_s)

        # --- seed project ---
        (tmpdir / "calc.py").write_text(_BUGGY_CALC, encoding="utf-8")
        (tmpdir / "test_calc.py").write_text(_TEST_CALC, encoding="utf-8")
        (tmpdir / "opencontext.yaml").write_text(_OC_YAML, encoding="utf-8")
        (tmpdir / "edits.json").write_text(_EDITS_JSON, encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="oc_bench_a2_home_") as fake_home:
            env = _isolated_env(fake_home)

            # --- run opencontext fix ---
            try:
                run_proc = subprocess.run(
                    [_CLI, "run", "Fix failing test", "--workflow", "oc-flow"],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(tmpdir),
                    env=env,
                    timeout=_TIMEOUT_RUN,
                )
            except subprocess.TimeoutExpired:
                return BenchmarkResult(
                    name=SUITE_ID,
                    success=False,
                    methodology_version=current_methodology_version(),
                    detail=f"opencontext run timed out after {_TIMEOUT_RUN}s",
                )
            except FileNotFoundError:
                return BenchmarkResult(
                    name=SUITE_ID,
                    success=False,
                    methodology_version=current_methodology_version(),
                    detail=f"opencontext CLI not found at {_CLI}; run pip install -e",
                )

            # Non-zero exit may be "needs_executor" etc. — preserved in metrics.
            run_exit = run_proc.returncode

            # --- verify the fix was applied by running pytest ---
            try:
                test_proc = subprocess.run(
                    [sys.executable, "-m", "pytest", "test_calc.py", "-q", "--tb=short"],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(tmpdir),
                    env=env,
                    timeout=_TIMEOUT_TEST,
                )
            except subprocess.TimeoutExpired:
                return BenchmarkResult(
                    name=SUITE_ID,
                    success=False,
                    methodology_version=current_methodology_version(),
                    detail=f"pytest verify timed out after {_TIMEOUT_TEST}s",
                )

            success = test_proc.returncode == 0
            test_out = (test_proc.stdout or test_proc.stderr).strip()
            detail = ""
            if not success:
                last = test_out.splitlines()[-1] if test_out else ""
                detail = (
                    f"pytest exit {test_proc.returncode}: {last} (opencontext run exit {run_exit})"
                )

            return BenchmarkResult(
                name=SUITE_ID,
                success=success,
                methodology_version=current_methodology_version(),
                detail=detail,
                metrics={
                    "run_returncode": run_exit,
                    "pytest_returncode": test_proc.returncode,
                },
            )

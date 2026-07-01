"""Environment proof baseline (commit-023).

The env proof script records the exact repository state (HEAD, sha256 of
key files, py_compile status, compileall status) BEFORE any code change
so future commits can attribute syntax errors to a specific delta.

See: openspec/changes/opencontext-runtime-convergence/tasks/commit-023-environment-proof.md
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "environment_proof.py"
JSON_OUT = REPO_ROOT / "artifacts" / "environment-proof.json"
TXT_OUT = REPO_ROOT / "artifacts" / "phase0-baseline.txt"

REQUIRED_FIELDS = {
    "schema_version",
    "git_head",
    "git_status",
    "python_version",
    "platform",
    "runner_sha256",
    "runner_py_compile_ok",
    "compileall_ok",
    "created_at",
    "notes",
}


def _run_proof_script() -> subprocess.CompletedProcess[str]:
    """Execute scripts/environment_proof.py as a subprocess."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_proof_script_exists() -> None:
    """The env proof script must exist on disk."""
    assert SCRIPT.exists(), f"missing script: {SCRIPT}"


def test_proof_script_emits_artifacts() -> None:
    """Running the script must produce both artifacts with the required JSON schema."""
    # Arrange: ensure artifacts dir is writable (script will create it).
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)

    # Act
    proc = _run_proof_script()

    # Assert: both artifacts produced
    assert JSON_OUT.exists(), (
        f"script did not produce {JSON_OUT}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert TXT_OUT.exists(), (
        f"script did not produce {TXT_OUT}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )

    # Assert: JSON parses and has every required field
    payload = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    missing = REQUIRED_FIELDS - set(payload.keys())
    assert not missing, f"missing JSON fields: {sorted(missing)}"

    # Assert: baseline text references the recorded sha256
    baseline_text = TXT_OUT.read_text(encoding="utf-8")
    assert "runner.py" in baseline_text, (
        f"baseline text does not mention runner.py:\n{baseline_text}"
    )
    assert str(payload["runner_sha256"]) in baseline_text, (
        "baseline text does not echo the runner sha256"
    )
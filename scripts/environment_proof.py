"""Environment proof baseline emitter (commit-023).

Records the exact repository state (HEAD, git status, sha256 of
runner.py, py_compile status, compileall status) BEFORE any code
change so future commits can attribute syntax errors to a specific
delta.

See: openspec/changes/opencontext-runtime-convergence/tasks/commit-023-environment-proof.md
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROOF = REPO_ROOT / "artifacts" / "environment-proof.json"
BASELINE = REPO_ROOT / "artifacts" / "phase0-baseline.txt"
RUNNER = REPO_ROOT / "packages" / "opencontext_core" / "opencontext_core" / "harness" / "runner.py"

SCHEMA_VERSION = "1.0"


def _run(cmd: list[str]) -> tuple[int, str]:
    """Run cmd, return (rc, stdout+stderr). Never raises on non-zero exit."""
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    PROOF.parent.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []

    git_rc, git_head = _run(["git", "rev-parse", "HEAD"])
    if git_rc != 0:
        notes.append(f"git rev-parse failed rc={git_rc}")

    _, git_status = _run(["git", "status", "--short"])

    runner_sha: str | None = None
    runner_py_compile_ok = False
    if RUNNER.exists():
        runner_sha = _sha256(RUNNER)
        rc, out = _run([sys.executable, "-m", "py_compile", str(RUNNER)])
        runner_py_compile_ok = rc == 0
        if not runner_py_compile_ok:
            notes.append(f"runner.py py_compile failed rc={rc}: {out}")
    else:
        notes.append(f"runner.py not found at {RUNNER}")

    compileall_rc, compileall_out = _run(
        [sys.executable, "-m", "compileall", "-q", "packages", "tests"]
    )
    compileall_ok = compileall_rc == 0
    if not compileall_ok:
        notes.append(f"compileall failed rc={compileall_rc}: {compileall_out}")

    proof = {
        "schema_version": SCHEMA_VERSION,
        "git_head": git_head,
        "git_status": git_status,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "runner_sha256": runner_sha,
        "runner_py_compile_ok": runner_py_compile_ok,
        "compileall_ok": compileall_ok,
        "created_at": datetime.now(UTC).isoformat(),
        "notes": notes,
    }

    PROOF.write_text(json.dumps(proof, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    notes_lines = [f"  - {n}" for n in notes] if notes else ["  (none)"]
    baseline_lines = [
        "OpenContext Runtime — Phase 0 environment baseline",
        f"schema_version: {proof['schema_version']}",
        f"created_at: {proof['created_at']}",
        f"git_head: {proof['git_head']}",
        f"python_version: {proof['python_version']}",
        f"platform: {proof['platform']}",
        f"runner.py path: {RUNNER}",
        f"runner.py sha256: {proof['runner_sha256']}",
        f"runner.py py_compile_ok: {proof['runner_py_compile_ok']}",
        f"compileall_ok: {proof['compileall_ok']}",
        "",
        "git status --short:",
        proof["git_status"] or "(clean)",
        "",
        "notes:",
        *notes_lines,
        "",
    ]
    BASELINE.write_text("\n".join(baseline_lines), encoding="utf-8")

    return 0 if (runner_py_compile_ok and compileall_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
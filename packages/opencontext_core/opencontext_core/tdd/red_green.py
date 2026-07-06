"""RED -> GREEN test-run evidence engine (TDD_STRICT_CONTRACT).

Captures machine-verified test-run evidence before (RED) and after (GREEN) a
mutation, and evaluates strict-mode violations as pure logic. OC Flow (`run`)
and the SDD harness surface this evidence in the persisted ``run.json`` ``tdd``
block; an already-passing test is never RED.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Bounded ceiling for one evidence test run (seconds).
DEFAULT_TEST_TIMEOUT = 120

#: Stable violation codes (CLI_CONTRACT error-code namespace).
TDD_NO_TEST_RUNNER = "TDD_NO_TEST_RUNNER"
TDD_RED_NOT_PROVEN = "TDD_RED_NOT_PROVEN"

#: Human-readable reasons per violation code.
VIOLATION_REASONS = {
    TDD_NO_TEST_RUNNER: (
        "TDD strict: no test runner or test files detected — a strict mutation run "
        "requires a failing test before any change"
    ),
    TDD_RED_NOT_PROVEN: (
        "TDD strict: the candidate test already passes — RED was not proven before the mutation"
    ),
}


@dataclass
class TddRunEvidence:
    """One executed test command with its honest outcome."""

    command: str
    exit_code: int
    failure_summary: str = ""
    captured_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "failure_summary": self.failure_summary,
            "captured_at": self.captured_at,
        }


@dataclass
class TddEvidence:
    """The run-level RED/GREEN evidence persisted under ``run.json`` ``tdd``."""

    mode: str = "ask"
    red: TddRunEvidence | None = None
    green: TddRunEvidence | None = None
    regression: TddRunEvidence | None = None
    violation: str | None = None

    @property
    def red_proven(self) -> bool:
        # An already-passing test is NOT RED (TDD_STRICT_CONTRACT policy table).
        return self.red is not None and self.red.exit_code != 0

    @property
    def green_proven(self) -> bool:
        return self.green is not None and self.green.exit_code == 0

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": self.mode,
            "red": self.red.to_json() if self.red else None,
            "green": self.green.to_json() if self.green else None,
            "regression": self.regression.to_json() if self.regression else None,
            "red_proven": self.red_proven,
            "green_proven": self.green_proven,
        }
        if self.violation:
            payload["violation"] = self.violation
        return payload


def capture_test_run(
    command: list[str], root: Path, *, timeout: int = DEFAULT_TEST_TIMEOUT
) -> TddRunEvidence:
    """Run *command* under *root* (bounded) and record honest evidence.

    The environment is sanitized the same way the OC Flow RED pre-check and the
    harness GREEN gate sanitize theirs: no parent-pytest leakage, no cached
    bytecode, and the project root importable.
    """
    env = {
        k: v for k, v in os.environ.items() if not (k.startswith("PYTEST_") or k.startswith("COV_"))
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) + (os.pathsep + existing_pp if existing_pp else "")
    captured_at = datetime.now(tz=UTC).isoformat()
    command_text = " ".join(str(part) for part in command)
    try:
        proc = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return TddRunEvidence(
            command=command_text,
            exit_code=-1,
            failure_summary=f"test run could not execute: {exc}",
            captured_at=captured_at,
        )
    return TddRunEvidence(
        command=command_text,
        exit_code=proc.returncode,
        failure_summary=_failure_summary(proc.stdout, proc.stderr, proc.returncode),
        captured_at=captured_at,
    )


def evaluate_strict(
    *, mutation_required: bool, has_test_command: bool, red: TddRunEvidence | None
) -> str | None:
    """Pure strict-mode gate: return a violation code, or None when clean.

    Contract table (TDD_STRICT_CONTRACT): no detectable test runner on a
    mutation task -> blocked; a candidate test that already passes is not RED.
    """
    if not mutation_required:
        return None
    if not has_test_command:
        return TDD_NO_TEST_RUNNER
    if red is not None and red.exit_code == 0:
        return TDD_RED_NOT_PROVEN
    return None


def _failure_summary(stdout: str, stderr: str, exit_code: int) -> str:
    if exit_code == 0:
        return ""
    lines = [ln for ln in f"{stdout}\n{stderr}".strip().splitlines() if ln.strip()]
    return "\n".join(lines[-5:])[:2000]

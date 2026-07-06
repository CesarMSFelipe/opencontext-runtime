"""RED -> GREEN test-run evidence engine (TDD_STRICT_CONTRACT).

Captures machine-verified test-run evidence before (RED) and after (GREEN) a
mutation, and evaluates strict-mode violations as pure logic. OC Flow (`run`)
and the SDD harness surface this evidence in the persisted ``run.json`` ``tdd``
block; an already-passing test is never RED, and neither is an environment or
usage error ("No module named pytest" exiting 1 proves nothing).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Bounded ceiling for one evidence test run (seconds).
DEFAULT_TEST_TIMEOUT = 120

#: Bounded ceiling for the runner-availability preflight (seconds).
PREFLIGHT_TIMEOUT = 30

#: Stable violation codes (CLI_CONTRACT error-code namespace).
TDD_NO_TEST_RUNNER = "TDD_NO_TEST_RUNNER"
TDD_RED_NOT_PROVEN = "TDD_RED_NOT_PROVEN"
TDD_TEST_ONLY_EDIT = "TDD_TEST_ONLY_EDIT"

#: Explicit strict-mode result for tasks with no applicable RED/GREEN cycle
#: (documentation / analysis / read-only tasks) — policy: never fake evidence.
TDD_NOT_APPLICABLE = "not_applicable"

#: Human-readable reasons per violation code.
VIOLATION_REASONS = {
    TDD_NO_TEST_RUNNER: (
        "TDD strict: no test runner or test files detected — a strict mutation run "
        "requires a failing test before any change"
    ),
    TDD_RED_NOT_PROVEN: (
        "TDD strict: the candidate test already passes — RED was not proven before the mutation"
    ),
    TDD_TEST_ONLY_EDIT: (
        "TDD strict: only test files were edited while the task required a functional "
        "change — rewriting tests to make them pass is suspicious, not a fix"
    ),
}

#: RED-run classification values (additive ``classification`` evidence field).
CLASSIFICATION_TEST_FAILURE = "test_failure"
CLASSIFICATION_ENVIRONMENT_ERROR = "environment_error"
CLASSIFICATION_NO_TESTS = "no_tests"
CLASSIFICATION_ALREADY_PASSING = "already_passing"

#: Output signatures of a broken runner/invocation — never a failing test.
#: Deliberately specific: an ImportError *inside* a test is a genuine RED
#: (classic TDD on a not-yet-written module); only the runner's own breakage
#: is an environment error.
_ENVIRONMENT_ERROR_SIGNATURES = (
    "No module named pytest",
    "error: unrecognized arguments",
    "ERROR: usage",
    "ERROR: file or directory not found",
)

#: Output evidence that tests actually EXECUTED and FAILED (pytest failure
#: lines / summary counts / assertion output).
_TEST_FAILURE_EVIDENCE_RE = re.compile(
    r"(?:^|\n)FAILED\b|\b\d+ failed\b|={3,} FAILURES ={3,}|\bAssertionError\b|\bassert\s"
)

#: Pytest exit code for an empty collection ("no tests ran").
_PYTEST_NO_TESTS_COLLECTED = 5

#: Paths that are test code: tests/** (or testing/**), test_*.py, *_test.py,
#: and conftest.py — the surface an executor could rewrite to game a RED test.
_TEST_PATH_RE = re.compile(
    r"(?:^|/)tests?/|(?:^|/)testing/|(?:^|/)test_[^/]+\.py$|(?:^|/)[^/]+_test\.py$"
    r"|(?:^|/)conftest\.py$"
)


def is_test_path(path: str) -> bool:
    """Whether *path* is test code (test file patterns or a tests directory)."""
    return bool(_TEST_PATH_RE.search(str(path).replace("\\", "/")))


def is_test_only_change(changed_files: list[str]) -> bool:
    """Whether a non-empty change set touches ONLY test code.

    Policy input for :data:`TDD_TEST_ONLY_EDIT`: a strict mutation run whose
    every edit lands in test files did not make the functional change the task
    required. An empty change set is a different (no-op) failure mode, never a
    test-only one.
    """
    files = [str(f) for f in changed_files]
    return bool(files) and all(is_test_path(f) for f in files)


def regression_command(test_command: list[str]) -> list[str]:
    """Derive the broader-suite command from a targeted test command (step 7).

    The contract's minimal-regression step re-runs the SAME runner without the
    targeted test selection (``.py`` paths / ``::`` node ids), so the runner
    collects the whole project. A command with no target arguments is already
    suite-wide and is reused as-is.
    """
    broad = [
        part
        for part in test_command
        if not (str(part).endswith(".py") or "::" in str(part) or is_test_path(str(part)))
    ]
    if broad and len(broad) < len(test_command):
        return broad
    return list(test_command)


def classify_test_run(exit_code: int, output: str) -> str:
    """Classify one pre-mutation test run for RED-evidence purposes.

    TDD_STRICT_CONTRACT: only a genuine executed-and-failed test proves RED.
    Environment/usage errors (missing runner module, unrecognized arguments,
    pytest exit codes 2/3/4), an empty collection (exit 5), and a green run
    can never be RED.
    """
    if exit_code == 0:
        return CLASSIFICATION_ALREADY_PASSING
    text = output or ""
    if any(signature in text for signature in _ENVIRONMENT_ERROR_SIGNATURES):
        return CLASSIFICATION_ENVIRONMENT_ERROR
    if exit_code == _PYTEST_NO_TESTS_COLLECTED:
        return CLASSIFICATION_NO_TESTS
    if exit_code == 1 and _TEST_FAILURE_EVIDENCE_RE.search(text):
        return CLASSIFICATION_TEST_FAILURE
    # Exit codes 2/3/4 (interrupted / internal / usage), signals, missing
    # binaries, and an exit 1 with no executed-and-failed evidence.
    return CLASSIFICATION_ENVIRONMENT_ERROR


def runner_available(command: list[str], *, timeout: int = PREFLIGHT_TIMEOUT) -> bool:
    """Preflight: can *command*'s test runner actually execute?

    ``<interpreter> -m <module> ...`` commands import the module in the SAME
    interpreter that would run the tests (so ``python -m pytest`` in a venv
    without pytest is caught before it fakes a RED). Plain binaries resolve on
    PATH. Unknown shapes stay optimistic — :func:`classify_test_run` on the
    captured output is the honest backstop.
    """
    if not command:
        return False
    if "-m" in command[1:]:
        module_index = command.index("-m", 1) + 1
        module = command[module_index] if module_index < len(command) else ""
        if module and all(part.isidentifier() for part in module.split(".")):
            try:
                proc = subprocess.run(
                    [command[0], "-c", f"import {module}"],
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                return False
            return proc.returncode == 0
    return shutil.which(command[0]) is not None


@dataclass
class TddRunEvidence:
    """One executed test command with its honest outcome."""

    command: str
    exit_code: int
    failure_summary: str = ""
    captured_at: str = ""
    #: RED classification (additive): test_failure | environment_error |
    #: no_tests | already_passing. Empty for evidence recorded before this
    #: field existed — derived from exit code + summary on read.
    classification: str = ""

    @property
    def effective_classification(self) -> str:
        """Recorded classification, derived from exit code + summary when absent."""
        return self.classification or classify_test_run(self.exit_code, self.failure_summary)

    def to_json(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "failure_summary": self.failure_summary,
            "captured_at": self.captured_at,
            "classification": self.effective_classification,
        }


@dataclass
class TddEvidence:
    """The run-level RED/GREEN evidence persisted under ``run.json`` ``tdd``."""

    mode: str = "ask"
    red: TddRunEvidence | None = None
    green: TddRunEvidence | None = None
    regression: TddRunEvidence | None = None
    violation: str | None = None
    #: Explicit strict-mode applicability result (additive): ``not_applicable``
    #: for documentation/read-only tasks where no RED/GREEN cycle applies.
    mode_result: str | None = None
    #: Human-readable justification for ``mode_result`` (policy: never a silent
    #: empty strict block).
    justification: str | None = None

    @property
    def red_proven(self) -> bool:
        # Only a genuine executed-and-failed test proves RED. An already-passing
        # test, an environment/usage error ("No module named pytest" exiting 1),
        # or an empty collection never does (TDD_STRICT_CONTRACT policy table).
        return (
            self.red is not None
            and self.red.effective_classification == CLASSIFICATION_TEST_FAILURE
        )

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
        if self.mode_result:
            payload["mode_result"] = self.mode_result
            payload["justification"] = self.justification or ""
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
            classification=CLASSIFICATION_ENVIRONMENT_ERROR,
        )
    return TddRunEvidence(
        command=command_text,
        exit_code=proc.returncode,
        failure_summary=_failure_summary(proc.stdout, proc.stderr, proc.returncode),
        captured_at=captured_at,
        classification=classify_test_run(proc.returncode, f"{proc.stdout}\n{proc.stderr}"),
    )


def evaluate_strict(
    *, mutation_required: bool, has_test_command: bool, red: TddRunEvidence | None
) -> str | None:
    """Pure strict-mode gate: return a violation code, or None when clean.

    Contract table (TDD_STRICT_CONTRACT): no detectable test runner on a
    mutation task -> blocked; a candidate test that already passes is not RED;
    an environment/usage error or an empty collection is not RED either — it
    routes to the same blocked/no-test-runner path.
    """
    if not mutation_required:
        return None
    if not has_test_command:
        return TDD_NO_TEST_RUNNER
    if red is not None:
        classification = red.effective_classification
        if classification == CLASSIFICATION_ALREADY_PASSING:
            return TDD_RED_NOT_PROVEN
        if classification in (CLASSIFICATION_ENVIRONMENT_ERROR, CLASSIFICATION_NO_TESTS):
            return TDD_NO_TEST_RUNNER
    return None


def _failure_summary(stdout: str, stderr: str, exit_code: int) -> str:
    if exit_code == 0:
        return ""
    lines = [ln for ln in f"{stdout}\n{stderr}".strip().splitlines() if ln.strip()]
    return "\n".join(lines[-5:])[:2000]

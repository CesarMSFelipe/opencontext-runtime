"""OC Flow local-first inspection (PR-007, FLOW-8, book doc 04 §11).

``local_inspection`` verifies a change LOCALLY, before any LLM spend, in the book
order: protocol -> path -> syntax -> AST guards -> secret scan -> lint -> typecheck
-> targeted tests -> broad tests -> quality gates. It spends **0 LLM tokens** and
emits exactly one typed outcome.

Syntax, AST and secret-scan checks are pure-Python and always run (the real
local-first gates). Lint/typecheck/test commands shell out only when explicitly
enabled (``run_external``) and a command is provided — kept off by default so the
inspection is deterministic and dependency-free.

Layering (doc 58): L9 importing L0/L4 safety only (downward).
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from opencontext_core.oc_flow.models import InspectionReport
from opencontext_core.safety.secrets import SecretScanner

# Outcome severity ranking — the worst observed gate determines the report outcome.
_PASSED = "passed"
_RECOVERABLE = "failed_recoverable"
_BLOCKING = "failed_blocking"


def _gate(name: str, status: str, message: str = "") -> dict[str, object]:
    return {"id": name, "status": status, "message": message}


def _check_path(root: Path, rel: str) -> dict[str, object] | None:
    """Path validation: a changed file must resolve under the run root."""
    try:
        (root / rel).resolve().relative_to(root.resolve())
    except ValueError:
        return _gate("path_validation", _BLOCKING, f"path escapes root: {rel}")
    return None


def _check_syntax(path: Path) -> dict[str, object] | None:
    """Syntax + AST guard: a .py file must parse."""
    if path.suffix != ".py" or not path.is_file():
        return None
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return _gate("syntax", _RECOVERABLE, f"{path.name}: {exc.msg} (line {exc.lineno})")
    return None


def _check_secrets(path: Path, scanner: SecretScanner) -> dict[str, object] | None:
    """Secret scan: a changed file must not introduce a secret (blocking)."""
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    findings = scanner.scan_secret_findings(text)
    if findings:
        kinds = ", ".join(sorted({f.kind for f in findings}))
        return _gate("secret_scan", _BLOCKING, f"{path.name}: secret(s) detected ({kinds})")
    return None


def _run_command(label: str, command: list[str], root: Path) -> dict[str, object]:
    """Run an external check; a non-zero exit is a recoverable failure.

    The executed command, its exit code and the capture time are recorded on the
    gate (additive keys) so the run report can persist real GREEN evidence.

    The child env is sanitized so the check leaves no residue in the user's
    project tree (PRODUCT_CONTRACT §Storage modes / AC-031): outer ``PYTEST_*``
    vars are stripped, ``PYTHONDONTWRITEBYTECODE=1`` suppresses ``__pycache__``,
    and ``PYTEST_ADDOPTS='-p no:cacheprovider'`` keeps pytest from writing
    ``.pytest_cache`` (ignored by non-pytest commands).
    """
    import os
    from datetime import UTC, datetime

    command_text = " ".join(str(part) for part in command)
    captured_at = datetime.now(tz=UTC).isoformat()
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_ADDOPTS"] = "-p no:cacheprovider"
    try:
        proc = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        gate = _gate(label, _RECOVERABLE, f"{label} could not run: {exc}")
        gate["command"] = command_text
        return gate
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
        gate = _gate(label, _RECOVERABLE, f"{label} failed: {tail[0][:200]}")
    else:
        gate = _gate(label, _PASSED, f"{label} passed")
    gate["command"] = command_text
    gate["exit_code"] = proc.returncode
    gate["captured_at"] = captured_at
    return gate


def _worst(gates: list[dict[str, object]]) -> str:
    """Reduce gate statuses to a single report outcome."""
    statuses = {str(g["status"]) for g in gates}
    if _BLOCKING in statuses:
        return _BLOCKING
    if _RECOVERABLE in statuses:
        return _RECOVERABLE
    return _PASSED


def run_local_inspection(
    root: Path,
    changed_files: list[str],
    *,
    test_command: list[str] | None = None,
    lint_command: list[str] | None = None,
    typecheck_command: list[str] | None = None,
    run_external: bool = False,
    mutation_required: bool = False,
) -> InspectionReport:
    """Run the zero-LLM local inspection over ``changed_files`` (FLOW-8).

    Returns an :class:`InspectionReport` whose ``outcome`` is the worst gate result
    and whose ``llm_tokens`` is always 0.

    When ``mutation_required`` is set, a run with NO changed files cannot satisfy the
    task: the ``scope`` gate is blocking (B1 / AVH-011), so inspection never reports
    ``passed`` for a no-op mutation. Read-only tasks keep the prior PASSED behaviour.
    """
    scanner = SecretScanner()
    gates: list[dict[str, object]] = [_gate("protocol_validation", _PASSED, "oc-flow protocol ok")]

    for rel in changed_files:
        if (g := _check_path(root, rel)) is not None:
            gates.append(g)
            continue
        path = (root / rel).resolve()
        if (g := _check_syntax(path)) is not None:
            gates.append(g)
        if (g := _check_secrets(path, scanner)) is not None:
            gates.append(g)

    # External, opportunistic checks (lint -> typecheck -> tests) — only when enabled.
    verified_by: list[str] = []
    verification_outcome = "not_run"
    if run_external:
        for label, command in (
            ("lint", lint_command),
            ("typecheck", typecheck_command),
            ("targeted_tests", test_command),
        ):
            if command:
                gate = _run_command(label, command, root)
                gates.append(gate)
                if label == "targeted_tests":
                    verified_by.append(" ".join(command))
                    verification_outcome = "passed" if gate["status"] == _PASSED else "failed"

    if mutation_required and test_command and verification_outcome == "not_run":
        gates.append(_gate("targeted_tests", _RECOVERABLE, "targeted tests did not run"))

    if not changed_files:
        if mutation_required:
            gates.append(_gate("scope", _BLOCKING, "mutation task produced no changed files"))
        else:
            gates.append(_gate("scope", _PASSED, "no changed files to inspect"))

    outcome = _worst(gates)
    failure = ""
    if outcome != _PASSED:
        failure = "; ".join(str(g["message"]) for g in gates if str(g["status"]) != _PASSED)

    return InspectionReport(
        outcome=outcome,  # type: ignore[arg-type]
        gate_results=gates,
        failure_summary=failure,
        verified_by=verified_by,
        verification_outcome=verification_outcome,
        llm_tokens=0,
    )

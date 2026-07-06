"""CLI truth layer: exit codes, error envelopes, canonical status, command registry.

Sprint 2 contract: every command outcome maps to one of nine canonical states,
each state maps to a documented exit code, and machine-facing errors share a
single JSON envelope shape.
"""

from __future__ import annotations

import argparse
import json
import sys

import pytest

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_exit_code_enum_values() -> None:
    from opencontext_cli.contracts.exit_codes import ExitCode

    assert ExitCode.OK == 0
    assert ExitCode.FAILURE == 1
    assert ExitCode.USAGE == 2
    assert ExitCode.CONFIG_INVALID == 3
    assert ExitCode.POLICY_BLOCKED == 4
    assert ExitCode.NEEDS_EXECUTOR == 5
    assert ExitCode.TDD_STRICT_VIOLATION == 6
    assert ExitCode.SDD_ARTIFACTS_MISSING == 7
    assert ExitCode.VERIFICATION_FAILED == 8
    assert ExitCode.INSTALL_INCOMPLETE == 9


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("passed", 0),
        ("not_applicable", 0),
        ("failed", 1),
        ("blocked", 1),
        ("needs_context", 1),
        ("cancelled", 1),
        ("needs_configuration", 3),
        ("needs_approval", 4),
        ("needs_executor", 5),
        ("no-such-status", 1),
        ("", 1),
    ],
)
def test_exit_code_for_status(status: str, expected: int) -> None:
    from opencontext_cli.contracts.exit_codes import exit_code_for_status

    assert exit_code_for_status(status) == expected


# ---------------------------------------------------------------------------
# Error / success envelopes
# ---------------------------------------------------------------------------


def test_error_envelope_full_shape() -> None:
    from opencontext_cli.contracts.error_envelope import error_envelope

    env = error_envelope(
        "TDD_RED_NOT_PROVEN",
        "TDD strict requires a failing test before mutation.",
        hint="Run the test first.",
        details={"workflow": "oc-flow", "phase": "apply"},
        status="blocked",
    )
    assert env == {
        "ok": False,
        "status": "blocked",
        "error": {
            "code": "TDD_RED_NOT_PROVEN",
            "message": "TDD strict requires a failing test before mutation.",
            "hint": "Run the test first.",
            "details": {"workflow": "oc-flow", "phase": "apply"},
        },
    }


def test_error_envelope_omits_none_hint_and_details() -> None:
    from opencontext_cli.contracts.error_envelope import error_envelope

    env = error_envelope("BOOM", "it broke")
    assert env["status"] == "failed"
    assert env["error"] == {"code": "BOOM", "message": "it broke"}
    assert "hint" not in env["error"]
    assert "details" not in env["error"]


def test_success_envelope_merges_data() -> None:
    from opencontext_cli.contracts.error_envelope import success_envelope

    env = success_envelope({"files": 3}, status="not_applicable")
    assert env == {"ok": True, "status": "not_applicable", "files": 3}
    default = success_envelope({})
    assert default == {"ok": True, "status": "passed"}


def test_envelopes_are_json_serializable() -> None:
    from opencontext_cli.contracts.error_envelope import error_envelope, success_envelope

    json.dumps(error_envelope("X", "y", hint="h", details={"a": 1}))
    json.dumps(success_envelope({"k": "v"}))


# ---------------------------------------------------------------------------
# Canonical status mapping (core layer)
# ---------------------------------------------------------------------------

CANONICAL_STATES = {
    "passed",
    "failed",
    "blocked",
    "needs_executor",
    "needs_approval",
    "needs_context",
    "needs_configuration",
    "not_applicable",
    "cancelled",
}


def test_canonical_status_members() -> None:
    from opencontext_core.models.canonical_status import CanonicalStatus

    assert {member.value for member in CanonicalStatus} == CANONICAL_STATES


@pytest.mark.parametrize("status", sorted(CANONICAL_STATES))
def test_to_canonical_identity(status: str) -> None:
    from opencontext_core.models.canonical_status import to_canonical

    assert to_canonical(status).value == status


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        ("completed", "passed"),
        ("warning", "passed"),
        ("done", "passed"),
        ("done_with_concerns", "passed"),
        ("ready", "passed"),
        ("halted", "blocked"),
        ("skipped", "not_applicable"),
        ("partial", "needs_configuration"),
        ("error", "failed"),
        ("policy_blocked", "needs_approval"),
        ("not_applied", "needs_executor"),
        ("totally-unknown", "failed"),
    ],
)
def test_to_canonical_legacy_values(legacy: str, expected: str) -> None:
    from opencontext_core.models.canonical_status import CanonicalStatus, to_canonical

    result = to_canonical(legacy)
    assert isinstance(result, CanonicalStatus)
    assert result.value == expected


# ---------------------------------------------------------------------------
# Command registry (contracts layer)
# ---------------------------------------------------------------------------

STABLE_COMMANDS = {
    "version",
    "doctor",
    "status",
    "init",
    "install",
    "uninstall",
    "clean",
    "config",
    "index",
    "pack",
    "run",
    "runs",
    "sdd",
    "harness",
    "memory",
    "knowledge-graph",
    "tui",
}


def _registered_commands() -> set[str]:
    from opencontext_cli.main import _build_parser

    parser = _build_parser()
    names: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            names.update(action.choices.keys())
    return names


def test_stable_set_is_exact() -> None:
    from opencontext_cli.contracts.command_registry import COMMAND_MATURITY

    stable = {cmd for cmd, level in COMMAND_MATURITY.items() if level == "stable"}
    assert stable == STABLE_COMMANDS


def test_every_registered_command_is_classified() -> None:
    from opencontext_cli.contracts.command_registry import COMMAND_MATURITY

    registered = _registered_commands()
    missing = sorted(registered - set(COMMAND_MATURITY))
    assert not missing, f"commands missing a contracts classification: {missing}"


def test_stable_commands_are_registered_or_planned() -> None:
    # "tui" is contract-stable but ships in a later sprint.
    registered = _registered_commands()
    unregistered = STABLE_COMMANDS - registered - {"tui"}
    assert not unregistered, f"stable commands not registered in the parser: {unregistered}"


def test_maturity_values_are_valid_and_default_is_preview() -> None:
    from opencontext_cli.contracts.command_registry import COMMAND_MATURITY, maturity

    invalid = {
        cmd: level
        for cmd, level in COMMAND_MATURITY.items()
        if level not in {"stable", "preview", "internal"}
    }
    assert not invalid
    assert maturity("status") == "stable"
    assert maturity("bytecode") == "internal"
    assert maturity("no-such-command") == "preview"


# ---------------------------------------------------------------------------
# CliContractError dispatch wiring
# ---------------------------------------------------------------------------


def test_cli_contract_error_envelope_and_exit_code() -> None:
    from opencontext_cli.contracts.errors import CliContractError

    err = CliContractError(
        "SDD_ARTIFACTS_MISSING",
        "spec artifact not found",
        hint="Run the spec phase first.",
        details={"change": "x"},
        status="needs_approval",
    )
    assert err.exit_code == 4
    env = err.to_envelope()
    assert env["ok"] is False
    assert env["status"] == "needs_approval"
    assert env["error"]["code"] == "SDD_ARTIFACTS_MISSING"
    assert env["error"]["hint"] == "Run the spec phase first."


def test_cli_contract_error_explicit_exit_code_wins() -> None:
    from opencontext_cli.contracts.errors import CliContractError

    err = CliContractError("TDD_RED_NOT_PROVEN", "no failing test", exit_code=6)
    assert err.exit_code == 6
    assert err.status == "failed"


def test_dispatcher_renders_contract_error_as_pure_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import opencontext_cli.main as m
    from opencontext_cli.contracts.errors import CliContractError

    def _raise(_args: object) -> None:
        raise CliContractError(
            "POLICY_BLOCKED",
            "policy denied the operation",
            hint="Ask an approver.",
            status="needs_approval",
        )

    monkeypatch.setattr(sys, "argv", ["opencontext", "status", "--json"])
    monkeypatch.setattr(m, "_dispatch", _raise)

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 4
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["status"] == "needs_approval"
    assert payload["error"]["code"] == "POLICY_BLOCKED"


def test_dispatcher_renders_contract_error_human_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import opencontext_cli.main as m
    from opencontext_cli.contracts.errors import CliContractError

    def _raise(_args: object) -> None:
        raise CliContractError("BOOM", "it broke badly", hint="try doctor")

    monkeypatch.setattr(sys, "argv", ["opencontext", "status"])
    monkeypatch.setattr(m, "_dispatch", _raise)

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "it broke badly" in captured.err

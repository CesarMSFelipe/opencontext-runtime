"""CLI-JSON-COMMON: every stable command failure in JSON mode emits the envelope.

CLI_CONTRACT.md frozen rule: with ``--json`` (or its ``OPENCONTEXT_JSON`` env
alias), stdout carries ONLY JSON, and every stable-command failure renders the
standard error envelope with a stable code — including failures that surface
as OpenContextError / FileNotFoundError / PermissionError / unexpected
exceptions in the top-level dispatcher.
"""

from __future__ import annotations

import json
import sys

import pytest

import opencontext_cli.main as m
from opencontext_core.errors import OpenContextError

# Minimal valid argv per stable command (tree commands include a subcommand).
SAMPLE_ARGV: dict[str, list[str]] = {
    "clean": ["clean"],
    "config": ["config"],
    "doctor": ["doctor"],
    "harness": ["harness", "list"],
    "index": ["index"],
    "init": ["init"],
    "install": ["install"],
    "knowledge-graph": ["knowledge-graph", "status"],
    "memory": ["memory", "list"],
    "pack": ["pack"],
    "run": ["run"],
    "runs": ["runs"],
    "sdd": ["sdd", "status"],
    "status": ["status"],
    "tui": ["tui"],
    "uninstall": ["uninstall"],
    "version": ["version"],
}


def _assert_error_envelope(stdout: str, *, code: str) -> dict:
    payload = json.loads(stdout)  # purity: stdout must be one JSON document
    assert payload["ok"] is False
    assert payload["status"] == "failed"
    error = payload["error"]
    assert error["code"] == code
    assert error["message"]
    return payload


def test_sample_argv_covers_every_stable_command() -> None:
    """CLI-JSON-COMMON: this matrix stays in lockstep with the stable registry."""
    from opencontext_cli.contracts.command_registry import COMMAND_MATURITY

    stable = {cmd for cmd, level in COMMAND_MATURITY.items() if level == "stable"}
    assert set(SAMPLE_ARGV) == stable


@pytest.mark.parametrize("command", sorted(SAMPLE_ARGV))
def test_stable_command_failure_emits_error_envelope_in_json_mode(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI-JSON-COMMON: a failing stable command in JSON mode emits the envelope."""
    monkeypatch.setattr(sys, "argv", ["opencontext", *SAMPLE_ARGV[command]])
    monkeypatch.setenv("OPENCONTEXT_JSON", "1")
    monkeypatch.delenv("OPENCONTEXT_DEBUG", raising=False)

    def _raise(_args: object) -> None:
        raise OpenContextError("boom")

    monkeypatch.setattr(m, "_dispatch", _raise)

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 1
    stdout = capsys.readouterr().out
    payload = _assert_error_envelope(stdout, code="OPERATION_FAILED")
    assert payload["error"]["message"] == "boom"
    assert payload["error"].get("hint"), "OPERATION_FAILED is P0: hint required"


def test_file_not_found_failure_uses_stable_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI-JSON-COMMON: FileNotFoundError in JSON mode renders FILE_NOT_FOUND."""
    monkeypatch.setattr(sys, "argv", ["opencontext", "status", "--json"])
    monkeypatch.delenv("OPENCONTEXT_JSON", raising=False)
    monkeypatch.delenv("OPENCONTEXT_DEBUG", raising=False)
    monkeypatch.setattr(m, "_dispatch", lambda _a: (_ for _ in ()).throw(FileNotFoundError("gone")))

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 1
    _assert_error_envelope(capsys.readouterr().out, code="FILE_NOT_FOUND")


def test_permission_denied_failure_uses_stable_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI-JSON-COMMON: PermissionError in JSON mode renders PERMISSION_DENIED."""
    monkeypatch.setattr(sys, "argv", ["opencontext", "status", "--json"])
    monkeypatch.delenv("OPENCONTEXT_JSON", raising=False)
    monkeypatch.delenv("OPENCONTEXT_DEBUG", raising=False)
    monkeypatch.setattr(m, "_dispatch", lambda _a: (_ for _ in ()).throw(PermissionError("denied")))

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 1
    _assert_error_envelope(capsys.readouterr().out, code="PERMISSION_DENIED")


def test_unexpected_failure_uses_stable_code_and_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI-JSON-COMMON: unexpected exceptions in JSON mode render UNEXPECTED_ERROR."""
    monkeypatch.setattr(sys, "argv", ["opencontext", "status", "--json"])
    monkeypatch.delenv("OPENCONTEXT_JSON", raising=False)
    monkeypatch.delenv("OPENCONTEXT_DEBUG", raising=False)
    monkeypatch.setattr(m, "_dispatch", lambda _a: (_ for _ in ()).throw(RuntimeError("weird")))

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 1
    payload = _assert_error_envelope(capsys.readouterr().out, code="UNEXPECTED_ERROR")
    assert payload["error"].get("hint"), "UNEXPECTED_ERROR is P0: hint required"


def test_human_mode_failure_output_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI-JSON-COMMON: without JSON mode, failures keep stderr text + empty stdout."""
    monkeypatch.setattr(sys, "argv", ["opencontext", "status"])
    monkeypatch.delenv("OPENCONTEXT_JSON", raising=False)
    monkeypatch.delenv("OPENCONTEXT_DEBUG", raising=False)
    monkeypatch.setattr(m, "_dispatch", lambda _a: (_ for _ in ()).throw(OpenContextError("boom")))

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "boom" in captured.err

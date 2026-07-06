"""`config explain --json` + CONFIG_INVALID envelope adoption (GAP-024 scope).

Invalid (unparseable) opencontext.yaml must raise ``CliContractError`` with
``code=CONFIG_INVALID`` / ``status=needs_configuration`` (exit code 3) from
config show/explain/doctor, and ``config explain --json`` must emit the
documented payload shape.
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from opencontext_cli.commands.config_cmd import handle_config
from opencontext_cli.contracts import CliContractError


def _write(root: Path, body: str) -> Path:
    path = root / "opencontext.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _args(command: str, **kwargs) -> Namespace:
    return Namespace(config_command=command, **kwargs)


def test_config_explain_json_emits_contract_payload(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))  # hermetic: no real global config
    _write(tmp_path, "version: 2\nproject:\n  name: demo\nharness:\n  tdd_mode: strict\n")
    handle_config(_args("explain", root=str(tmp_path), json=True))
    payload = json.loads(capsys.readouterr().out)
    for field in (
        "effective_config",
        "sources",
        "conflicts",
        "deprecated_keys",
        "unknown_keys",
        "validation",
    ):
        assert field in payload, f"missing contract field: {field}"
    assert payload["validation"]["status"] == "passed"
    assert payload["sources"]["harness.tdd_mode"]["source"] == "project"


def test_config_explain_invalid_yaml_raises_config_invalid(tmp_path: Path) -> None:
    _write(tmp_path, "version: [unclosed\n  broken")
    with pytest.raises(CliContractError) as excinfo:
        handle_config(_args("explain", root=str(tmp_path), json=True))
    err = excinfo.value
    assert err.code == "CONFIG_INVALID"
    assert err.status == "needs_configuration"
    assert err.exit_code == 3
    assert err.hint


def test_config_show_invalid_yaml_raises_config_invalid(tmp_path: Path) -> None:
    _write(tmp_path, "version: [unclosed\n  broken")
    with pytest.raises(CliContractError) as excinfo:
        handle_config(_args("show", root=str(tmp_path), json=True))
    err = excinfo.value
    assert err.code == "CONFIG_INVALID"
    assert err.exit_code == 3


def test_config_doctor_invalid_yaml_raises_config_invalid(tmp_path: Path) -> None:
    _write(tmp_path, "version: [unclosed\n  broken")
    with pytest.raises(CliContractError) as excinfo:
        handle_config(_args("doctor", root=str(tmp_path), json=True, strict=False))
    err = excinfo.value
    assert err.code == "CONFIG_INVALID"
    assert err.status == "needs_configuration"
    assert err.exit_code == 3


def test_config_explain_envelope_shape_matches_contract(tmp_path: Path) -> None:
    _write(tmp_path, "version: [unclosed\n  broken")
    with pytest.raises(CliContractError) as excinfo:
        handle_config(_args("explain", root=str(tmp_path), json=True))
    envelope = excinfo.value.to_envelope()
    assert envelope["ok"] is False
    assert envelope["status"] == "needs_configuration"
    assert envelope["error"]["code"] == "CONFIG_INVALID"
    assert envelope["error"]["message"]
    assert envelope["error"]["hint"]

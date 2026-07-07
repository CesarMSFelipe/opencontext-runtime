"""CFG-003 / LAYERS-ORDER: real CLI flags feed the resolver's override layers.

``opencontext config explain`` ships ``--profile``, ``--set KEY=VALUE`` (plan §6
layer 7, CLI flags) and ``--run-override KEY=VALUE`` (plan §6 layer 8, temporary
run overrides). These must beat ``OPENCONTEXT_*`` env vars end-to-end through
the shipped command handler, with provenance naming the winning layer.
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


def _args(**kwargs) -> Namespace:
    defaults = {
        "config_command": "explain",
        "json": True,
        "profile": None,
        "set_overrides": [],
        "run_overrides": [],
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


@pytest.fixture()
def hermetic_ws(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))  # no real global config
    monkeypatch.delenv("OPENCONTEXT_ORG_CONFIG", raising=False)
    monkeypatch.delenv("OPENCONTEXT_PROFILE", raising=False)
    monkeypatch.delenv("OPENCONTEXT_UI_LANGUAGE", raising=False)
    _write(tmp_path, "version: 2\nproject:\n  name: demo\n")
    return tmp_path


def _explain_payload(capsys, **kwargs) -> dict:
    handle_config(_args(**kwargs))
    return json.loads(capsys.readouterr().out)


def test_profile_flag_beats_env(hermetic_ws: Path, capsys, monkeypatch) -> None:
    """CFG-003: `config explain --profile` beats OPENCONTEXT_PROFILE end-to-end via the CLI."""
    monkeypatch.setenv("OPENCONTEXT_PROFILE", "low-cost")
    payload = _explain_payload(capsys, root=str(hermetic_ws), profile="performance")
    assert payload["profile"] == "performance"
    assert payload["sources"]["profile"]["source"] == "overrides"
    # performance overlay routes providers to fastest (proof the flag drove resolution).
    assert payload["effective_config"]["providers"]["strategy"] == "fastest"


def test_set_flag_beats_env(hermetic_ws: Path, capsys, monkeypatch) -> None:
    """CFG-003: `config explain --set KEY=VALUE` beats the matching OPENCONTEXT_* env var."""
    monkeypatch.setenv("OPENCONTEXT_UI_LANGUAGE", "es")
    payload = _explain_payload(capsys, root=str(hermetic_ws), set_overrides=["ui_language=en"])
    assert payload["effective_config"]["ui_language"] == "en"
    assert payload["sources"]["ui_language"]["source"] == "overrides"


def test_run_override_flag_beats_set_flag(hermetic_ws: Path, capsys) -> None:
    """LAYERS-ORDER: `--run-override` (doc layer 8) beats `--set` (doc layer 7) via the CLI."""
    payload = _explain_payload(
        capsys,
        root=str(hermetic_ws),
        set_overrides=["ui_language=en"],
        run_overrides=["ui_language=fr"],
    )
    assert payload["effective_config"]["ui_language"] == "fr"
    assert payload["sources"]["ui_language"]["source"] == "run"


def test_malformed_set_pair_fails_with_contract_error(hermetic_ws: Path) -> None:
    """CFG-003: a `--set` pair without '=' fails with the CONFIG_INVALID contract envelope."""
    with pytest.raises(CliContractError) as excinfo:
        handle_config(_args(root=str(hermetic_ws), set_overrides=["ui_language"]))
    assert excinfo.value.code == "CONFIG_INVALID"
    assert "--set" in excinfo.value.message

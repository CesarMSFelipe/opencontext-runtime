"""Tests for the `opencontext models` command (model routing front door)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from opencontext_cli.commands.models_cmd import handle_models


def _init(tmp_path: Path) -> Path:
    cfg = tmp_path / "opencontext.yaml"
    cfg.write_text(yaml.safe_dump({"project": {"name": "t"}}), encoding="utf-8")
    return cfg


def _read(cfg: Path) -> dict:
    return yaml.safe_load(cfg.read_text(encoding="utf-8"))


def test_set_persona_writes_persona_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _init(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = handle_models(
        SimpleNamespace(models_command="set-persona", persona="architect", model="opus")
    )
    assert rc == 0
    # Written under sdd.persona_models keyed by the persona id the runner reads.
    assert _read(cfg)["sdd"]["persona_models"]["oc-architect"] == "opus"


def test_set_default_writes_default_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _init(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = handle_models(SimpleNamespace(models_command="set-default", model="sonnet"))
    assert rc == 0
    assert _read(cfg)["models"]["default"]["model"] == "sonnet"


def test_set_role_still_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _init(tmp_path)
    monkeypatch.chdir(tmp_path)
    rc = handle_models(SimpleNamespace(models_command="set-role", role="generate", model="opus"))
    assert rc == 0
    assert _read(cfg)["models"]["roles"]["generate"]["model"] == "opus"


def test_show_returns_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _init(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert handle_models(SimpleNamespace(models_command="show")) == 0


def test_no_config_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # no opencontext.yaml
    assert handle_models(SimpleNamespace(models_command="show")) == 1

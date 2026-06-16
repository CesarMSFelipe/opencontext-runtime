"""`config set` of a runtime-affecting key reaches the project opencontext.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opencontext_cli.commands import config_cmd
from opencontext_core.config import default_config_data
from opencontext_core.user_prefs import UserConfigStore


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate user-prefs from real $HOME and run inside a tmp project.
    cfg_dir = tmp_path / "home" / ".config" / "opencontext"
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", cfg_dir / "user-config.json")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "opencontext.yaml").write_text(
        yaml.safe_dump(default_config_data(), sort_keys=False), encoding="utf-8"
    )


def _yaml(tmp_path: Path) -> dict:
    return yaml.safe_load((tmp_path / "opencontext.yaml").read_text(encoding="utf-8"))


def test_config_set_bridges_runtime_key_to_yaml(tmp_path: Path) -> None:
    config_cmd._config_set("features.embeddings", "true")
    assert _yaml(tmp_path)["embedding"]["enabled"] is True


def test_config_set_provider_reaches_yaml(tmp_path: Path) -> None:
    config_cmd._config_set("default_provider", "anthropic")
    assert _yaml(tmp_path)["models"]["default"]["provider"] == "anthropic"


def test_invalid_value_reverts_yaml_never_corrupts(tmp_path: Path) -> None:
    before = (tmp_path / "opencontext.yaml").read_text(encoding="utf-8")
    config_cmd._config_set("security_mode", "not_a_real_mode")
    # The project yaml must still be exactly what it was (reverted) and still load.
    assert (tmp_path / "opencontext.yaml").read_text(encoding="utf-8") == before


def test_prefs_only_key_does_not_touch_yaml(tmp_path: Path) -> None:
    before = (tmp_path / "opencontext.yaml").read_text(encoding="utf-8")
    config_cmd._config_set("check_updates", "false")  # not in the yaml mapping
    assert (tmp_path / "opencontext.yaml").read_text(encoding="utf-8") == before

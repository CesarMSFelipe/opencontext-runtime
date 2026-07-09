"""F3: config set/get on unknown yaml-section keys must hint at opencontext.yaml.

Keys that start with known yaml section prefixes (runtime., memory., storage., sdd.,
context., models., security.) but are not in the 22-key CONFIG_PATHS whitelist live in
opencontext.yaml, not in user-prefs.  The CLI must say so clearly instead of listing
all available paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_cli.commands import config_cmd
from opencontext_core.user_prefs import UserConfigStore


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_dir = tmp_path / "home" / ".config" / "opencontext"
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", cfg_dir / "user-config.json")
    monkeypatch.chdir(tmp_path)


def test_config_set_yaml_section_key_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """config set runtime.oc_flow_enabled must exit non-zero with an opencontext.yaml hint."""
    with pytest.raises(SystemExit) as exc_info:
        config_cmd._config_set("runtime.oc_flow_enabled", "true")
    assert exc_info.value.code != 0, "Expected non-zero exit for yaml-section key"
    err = capsys.readouterr().err
    assert "opencontext.yaml" in err, (
        f"Expected hint mentioning 'opencontext.yaml' in stderr.\nGot:\n{err}"
    )


def test_config_get_yaml_section_key_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """config get memory.provider must exit non-zero with an opencontext.yaml hint."""
    with pytest.raises(SystemExit) as exc_info:
        config_cmd._config_get("memory.provider")
    assert exc_info.value.code != 0, "Expected non-zero exit for yaml-section key"
    err = capsys.readouterr().err
    assert "opencontext.yaml" in err, (
        f"Expected hint mentioning 'opencontext.yaml' in stderr.\nGot:\n{err}"
    )


def test_config_set_whitelist_key_unchanged(tmp_path: Path) -> None:
    """config set with a key in CONFIG_PATHS still works (no regression)."""
    # sdd.tdd_mode IS in CONFIG_PATHS — must not be affected by the new guard.
    config_cmd._config_set("sdd.tdd_mode", "off")
    # If we got here without SystemExit the guard did not fire (correct).


def test_config_set_truly_unknown_key_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """config set with a key that is not a yaml section AND not in whitelist stays as 'Unknown key'.

    Non-yaml-section unknown keys do NOT trigger the yaml hint — they get the standard
    'Unknown key' listing.  No SystemExit required by this path (existing behavior kept).
    """
    config_cmd._config_set("totally_unknown_xyz", "val")
    err = capsys.readouterr().err
    # Should still report an error (Unknown key), not the yaml hint
    assert "totally_unknown_xyz" in err or "Unknown" in err
    assert "opencontext.yaml" not in err, "Non-yaml-section key must not emit the yaml hint"

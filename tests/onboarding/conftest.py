"""Shared isolation for the onboarding suite.

Onboarding writes to two locations outside the project root: the install state
under ``Path.home()`` and user preferences under ``UserConfigStore.CONFIG_DIR``
(both default into the developer's real ``~/.config``). Redirect both to tmp so
no onboarding test can pollute the real home.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.user_prefs import UserConfigStore


@pytest.fixture(autouse=True)
def isolate_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Do not pre-create the dir: consumers mkdir(parents=True) as needed, and a
    # few tests create tmp_path/"home" themselves (a pre-created dir would clash).
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)

    config_dir = home / ".config" / "opencontext"
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", config_dir / "user-config.json")

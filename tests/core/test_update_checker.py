"""Tests for UpdateChecker version handling."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from opencontext_core import update as update_module
from opencontext_core.update import UpdateCheck, UpdateChecker, UpdateState


def test_compare_versions_handles_prerelease_tags() -> None:
    # Regression: a bare int() parse crashed on PEP 440 pre-releases like '0.2.1b0',
    # and the swallowed exception hid every update from pre-release installs.
    assert UpdateChecker._compare_versions("0.2.1b0", "1.2.0") == -1
    assert UpdateChecker._compare_versions("1.2.0", "0.2.1b0") == 1
    assert UpdateChecker._compare_versions("1.0.0b1", "1.0.0") == -1  # pre < final
    assert UpdateChecker._compare_versions("1.2.0", "1.2.0") == 0
    assert UpdateChecker._compare_versions("1.2.0", "1.10.0") == -1  # numeric, not lexical


def test_check_busts_cache_when_installed_version_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A fresh cache that records a different installed version must not be returned,
    # else `update` echoes a stale number that contradicts `--version`.
    monkeypatch.setattr(UpdateChecker, "CACHE_FILE", tmp_path / "update-cache.json")
    monkeypatch.setattr(UpdateChecker, "get_current_version", classmethod(lambda cls: "0.2.1b0"))

    now = datetime.now().isoformat()
    stale = UpdateState(
        check=UpdateCheck(current_version="0.0.1", latest_version="0.0.1", is_outdated=False),
        last_check=now,
    )
    UpdateChecker._save_cache(stale)

    def _offline(*_args: object, **_kwargs: object) -> object:
        raise OSError("network disabled in test")

    monkeypatch.setattr(update_module, "urlopen", _offline)

    result = UpdateChecker.check()
    # Live version reported, not the stale cached "0.0.1".
    assert result.current_version == "0.2.1b0"

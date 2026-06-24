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


def _stale_cache(monkeypatch, tmp_path, *, latest: str, live: str) -> None:
    monkeypatch.setattr(UpdateChecker, "CACHE_FILE", tmp_path / "update-cache.json")
    monkeypatch.setattr(UpdateChecker, "get_current_version", classmethod(lambda cls: live))
    UpdateChecker._save_cache(
        UpdateState(
            check=UpdateCheck(current_version="1.0.1", latest_version=latest, is_outdated=True),
            last_check=datetime.now().isoformat(),
        )
    )
    from opencontext_core.update import EcosystemUpdateChecker

    monkeypatch.setattr(EcosystemUpdateChecker, "check_cached", classmethod(lambda cls: []))


def test_pending_update_notices_suppressed_when_live_is_current(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The bug: a stale cache (1.0.1 -> 1.2.0) nagged a 1.5.0 install forever. The
    # notice must re-validate the cached latest against the LIVE version.
    from opencontext_core.update import pending_update_notices

    _stale_cache(monkeypatch, tmp_path, latest="1.2.0", live="1.5.0")
    assert pending_update_notices() == []


def test_pending_update_notices_shown_and_uses_live_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from opencontext_core.update import pending_update_notices

    _stale_cache(monkeypatch, tmp_path, latest="1.6.0", live="1.5.0")
    notices = pending_update_notices()
    assert any("1.5.0 -> 1.6.0" in n for n in notices)  # live version, not cached 1.0.1

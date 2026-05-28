"""Tests for first-run detection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opencontext_core.onboarding.service import is_first_run


class TestFirstRunDetection:
    """First-run detection logic tests."""

    def test_no_config_file_is_first_run(self, tmp_path: Path) -> None:
        """No opencontext.yaml means it's a first run."""
        assert is_first_run(tmp_path) is True

    def test_config_without_setup_is_first_run(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Config exists but setup_completed is False (incomplete setup)."""
        from opencontext_core.user_prefs import UserConfigStore

        config = tmp_path / "opencontext.yaml"
        config.write_text("security:\n  mode: private_project\n", encoding="utf-8")

        # Mock UserConfigStore to return setup_completed=False
        config_dir = tmp_path / "config"
        monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", config_dir / "user-config.json")
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "user-config.json").write_text('{"setup_completed": false}', encoding="utf-8")

        assert is_first_run(tmp_path) is True

    def test_config_with_setup_completed_is_not_first_run(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Config exists AND setup_completed → not first run."""
        from opencontext_core.user_prefs import UserConfigStore

        config = tmp_path / "opencontext.yaml"
        config.write_text("security:\n  mode: private_project\n", encoding="utf-8")

        # Mock UserConfigStore to return setup_completed=True
        config_dir = tmp_path / "config"
        monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", config_dir / "user-config.json")

        prefs_dir = config_dir
        prefs_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "user-config.json").write_text(
            json.dumps({"setup_completed": True}), encoding="utf-8"
        )

        assert is_first_run(tmp_path) is False

    def test_detection_handles_missing_user_config(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Missing user config with existing project config → first run (setup not completed)."""
        from opencontext_core.user_prefs import UserConfigStore

        config = tmp_path / "opencontext.yaml"
        config.write_text("version: 0.1\n", encoding="utf-8")

        # Mock UserConfigStore to point to non-existent config
        config_dir = tmp_path / "config"
        monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", config_dir / "user-config.json")
        # Don't create dir — UserConfigStore will create defaults with setup_completed=False

        result = is_first_run(tmp_path)
        assert result is True  # setup_completed defaults to False → first run

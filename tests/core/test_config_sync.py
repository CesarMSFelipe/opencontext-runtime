"""Core prefs->yaml sync: validated, revert-on-failure, used by config set + wizard."""

from __future__ import annotations

from pathlib import Path

import yaml

from opencontext_core.config import default_config_data
from opencontext_core.config_sync import sync_pref_to_yaml, sync_runtime_prefs_to_yaml
from opencontext_core.user_prefs import UserPreferences


def _project(tmp_path: Path) -> Path:
    (tmp_path / "opencontext.yaml").write_text(
        yaml.safe_dump(default_config_data(), sort_keys=False), encoding="utf-8"
    )
    return tmp_path


def _loaded(tmp_path: Path) -> dict:
    return yaml.safe_load((tmp_path / "opencontext.yaml").read_text(encoding="utf-8"))


def test_sync_pref_patches_mapped_key(tmp_path: Path) -> None:
    _project(tmp_path)
    assert sync_pref_to_yaml("features.embeddings", True, root=tmp_path) is True
    assert _loaded(tmp_path)["embedding"]["enabled"] is True


def test_sync_pref_unmapped_key_is_noop(tmp_path: Path) -> None:
    _project(tmp_path)
    assert sync_pref_to_yaml("check_updates", False, root=tmp_path) is False


def test_runtime_feature_keys_reach_the_yaml(tmp_path: Path) -> None:
    """Expanded bridge: runtime-affecting feature toggles now reach opencontext.yaml."""
    _project(tmp_path)
    assert sync_pref_to_yaml("features.mcp_server", False, root=tmp_path) is True
    assert sync_pref_to_yaml("features.knowledge_graph", False, root=tmp_path) is True
    assert sync_pref_to_yaml("features.semantic_search", False, root=tmp_path) is True
    data = _loaded(tmp_path)
    assert data["tools"]["mcp"]["enabled"] is False
    assert data["knowledge_graph"]["enabled"] is False
    assert data["cache"]["semantic"]["enabled"] is False


def test_sync_pref_invalid_value_reverts(tmp_path: Path) -> None:
    _project(tmp_path)
    before = (tmp_path / "opencontext.yaml").read_text(encoding="utf-8")
    assert sync_pref_to_yaml("security_mode", "bogus_mode", root=tmp_path) is False
    assert (tmp_path / "opencontext.yaml").read_text(encoding="utf-8") == before


def test_sync_pref_no_project_config_is_noop(tmp_path: Path) -> None:
    # No opencontext.yaml under root -> nothing to patch.
    assert sync_pref_to_yaml("features.embeddings", True, root=tmp_path) is False


def test_sync_all_runtime_prefs_from_prefs_object(tmp_path: Path) -> None:
    _project(tmp_path)
    prefs = UserPreferences()
    prefs.features.embeddings = True
    prefs.default_provider = "anthropic"

    applied = sync_runtime_prefs_to_yaml(prefs, root=tmp_path)

    data = _loaded(tmp_path)
    assert data["embedding"]["enabled"] is True
    assert data["models"]["default"]["provider"] == "anthropic"
    assert "embedding.enabled" in applied and "models.default.provider" in applied


def test_fill_only_does_not_stomp_explicit_project_provider(tmp_path: Path) -> None:
    """Real-use regression: install bridged the global mock prefs over a
    hand-written ollama models.default. Fill-only must leave the explicit value
    and still gap-fill keys the project omitted."""
    (tmp_path / "opencontext.yaml").write_text(
        "project:\n  name: t\n"
        "models:\n  default:\n    provider: ollama\n    model: qwen2.5:7b-instruct\n",
        encoding="utf-8",
    )
    prefs = UserPreferences()  # global default provider is mock
    prefs.features.embeddings = True

    sync_runtime_prefs_to_yaml(prefs, root=tmp_path, overwrite=False)

    data = _loaded(tmp_path)
    assert data["models"]["default"]["provider"] == "ollama"  # explicit value kept
    assert data["models"]["default"]["model"] == "qwen2.5:7b-instruct"
    assert data["embedding"]["enabled"] is True  # absent key still gap-filled

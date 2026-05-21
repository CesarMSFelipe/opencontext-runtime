from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opencontext_core.config import (
    ArtifactStoreMode,
    SDDConfig,
    default_config_data,
    load_config,
)
from opencontext_core.errors import ConfigurationError


def test_config_loading_merges_required_ignore_patterns(tmp_path: Path) -> None:
    data = default_config_data()
    data["project_index"]["ignore"] = ["custom-cache"]
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    config = load_config(config_path)

    assert config.project.name == "example-project"
    assert "custom-cache" in config.project_index.ignore
    assert "dist" in config.project_index.ignore
    assert config.models.default.provider == "mock"


def test_missing_config_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="Configuration file not found"):
        load_config(tmp_path / "missing.yaml")


def test_new_config_models_load_with_defaults() -> None:
    config = load_config()

    # SDD config
    assert config.sdd.artifact_store.mode == "none"
    assert config.sdd.delivery_strategy == "plan-only"
    assert config.sdd.chain_strategy == "stacked-to-main"
    assert config.sdd.model_assignments["explore"] == "default"
    assert config.sdd.model_assignments["archive"] == "default"
    assert config.sdd.interactive is False

    # Knowledge graph config
    assert config.knowledge_graph.enabled is True
    assert config.knowledge_graph.languages == []
    assert config.knowledge_graph.exclude
    assert config.knowledge_graph.max_file_size == 1_048_576
    assert config.knowledge_graph.track_call_sites is True
    assert config.knowledge_graph.auto_sync is True
    assert config.knowledge_graph.track_class_hierarchy is True

    # Skills config
    assert config.skills.enabled is False
    assert config.skills.registry_path == ".atl/skill-registry.md"
    assert config.skills.auto_discover is True
    assert "~/.config/opencode/skills/" in config.skills.user_dirs
    assert ".claude/skills/" in config.skills.project_dirs


def test_config_with_new_sections_loads(tmp_path: Path) -> None:
    data = default_config_data()
    data["sdd"]["delivery_strategy"] = "auto-chain"
    data["knowledge_graph"]["enabled"] = True
    data["knowledge_graph"]["languages"] = ["python", "typescript"]
    data["skills"]["enabled"] = True
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    config = load_config(config_path)

    assert config.sdd.delivery_strategy == "auto-chain"
    assert config.knowledge_graph.enabled is True
    assert config.knowledge_graph.languages == ["python", "typescript"]
    assert config.skills.enabled is True


def test_model_assignments_override(tmp_path: Path) -> None:
    data = default_config_data()
    data["sdd"]["model_assignments"]["apply"] = "cheap"
    data["sdd"]["model_assignments"]["verify"] = "expensive"
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    config = load_config(config_path)

    assert config.sdd.model_assignments["apply"] == "cheap"
    assert config.sdd.model_assignments["verify"] == "expensive"
    assert config.sdd.model_assignments["explore"] == "default"


def test_artifact_store_mode_engram() -> None:
    sdd = SDDConfig(artifact_store={"mode": "engram", "engram": {"project": "my-project"}})
    assert sdd.artifact_store.mode == ArtifactStoreMode.ENGRAM
    assert sdd.artifact_store.engram.project == "my-project"


def test_backward_compat_old_config_ignores_new_sections() -> None:
    config = load_config()
    assert config.project.name
    assert config.context.max_input_tokens
    assert config.models.default.provider

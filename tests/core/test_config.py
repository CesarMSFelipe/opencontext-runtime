from __future__ import annotations

import base64
import importlib
import json
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
from opencontext_core.models.context import CompressionStrategy


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


def test_vector_defaults_are_local_noop_and_opt_in() -> None:
    data = default_config_data()
    config = load_config()

    assert data["embedding"]["enabled"] is False
    assert data["embedding"]["provider"] == "local"
    assert data["embedding"]["storage_backend"] == "null"
    assert config.embedding.enabled is False
    assert config.embedding.storage_backend == "null"


# Base64-encoded so the blocked names appear nowhere as plaintext in this repo or
# its history, while the guard still decodes and blocks them in public surfaces.
_FORBIDDEN_B64 = (
    "Z2VudGxlLWFp",
    "Z2VudGxlIGFp",
    "Z2VudGxlYWk=",
    "Z3JhcGhpZnk=",
    "Y29kZWdyYXBo",
    "cWRyYW50",
    "bGxtbGluZ3Vh",
    "Y2F2ZW1hbg==",
    "cG9ueXRhaWw=",
)


def _forbidden_external_names() -> tuple[str, ...]:
    """External product/tool names that must not appear in public surfaces.

    Decoded from ``_FORBIDDEN_B64`` so the names never appear as plaintext in the
    repository (or its history), while the guard still blocks every spelling.
    """
    return tuple(base64.b64decode(b).decode() for b in _FORBIDDEN_B64)


def test_public_default_config_uses_generic_names() -> None:
    rendered = json.dumps(default_config_data()).lower()

    for forbidden in _forbidden_external_names():
        assert forbidden not in rendered


def test_public_surfaces_do_not_expose_external_names() -> None:
    root = Path(__file__).parents[2]
    public_files = [
        root / "README.md",
        root / "opencontext.yaml",
        root / "packages/opencontext_cli/opencontext_cli/main.py",
        root / "packages/opencontext_core/opencontext_core/mcp_stdio.py",
        root / "packages/opencontext_core/opencontext_core/runtime/__init__.py",
        *sorted((root / "packages/opencontext_core/opencontext_core/indexing").glob("*.py")),
        # Shipped docs only; the internal planning corpus (architecture book) and the
        # research/investigation notes under docs/inv/ are not public surfaces and
        # intentionally reference external systems for comparison.
        *sorted(
            p
            for p in (root / "docs").rglob("*.md")
            if "OpenContext_Complete_Plans_and_Architecture_Book" not in p.parts
            and "inv" not in p.parts
        ),
        *sorted((root / "examples").rglob("opencontext.yaml")),
    ]
    public_text = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in public_files if path.exists()
    )
    exported = importlib.import_module("opencontext_core.compression.terse")
    symbol_text = "\n".join(
        [
            *getattr(exported, "__all__", ()),
            *[strategy.name for strategy in CompressionStrategy],
            *[strategy.value for strategy in CompressionStrategy],
        ]
    ).lower()

    scanned = f"{public_text}\n{symbol_text}"
    for forbidden in _forbidden_external_names():
        assert forbidden not in scanned


def test_legacy_terse_intensity_key_loads_without_public_default(tmp_path: Path) -> None:
    data = default_config_data()
    legacy_key = "cave" + "man_intensity"
    data["context"]["compression"][legacy_key] = "lite"
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    config = load_config(config_path)

    assert config.context.compression.terse_intensity == "lite"


def test_testing_config_defaults() -> None:
    from opencontext_core.config import MutationConfig, TestingConfig

    cfg = TestingConfig()
    assert cfg.mutation.enabled is False
    assert cfg.mutation.threshold == 80
    assert cfg.mutation.fail_on_low_score is False
    assert isinstance(cfg.mutation, MutationConfig)


def test_context_planning_config_defaults() -> None:
    from opencontext_core.config import ContextPlanningConfig

    cfg = ContextPlanningConfig()
    assert cfg.enabled is True
    assert cfg.default_mode == "progressive"
    assert cfg.contract_required is True
    assert cfg.risk_classifier == "deterministic"
    assert cfg.max_expansion_rounds == 3
    assert cfg.fail_on_unverified_critical_assumptions is False


def test_opencontext_config_accepts_new_fields() -> None:
    from opencontext_core.config import OpenContextConfig, default_config_data

    data = default_config_data()
    config = OpenContextConfig.model_validate(data)
    # New fields present with defaults
    assert hasattr(config, "testing")
    assert hasattr(config, "context_planning")
    assert hasattr(config, "context_storage")
    assert config.testing.mutation.enabled is False
    assert config.context_planning.enabled is True
    assert config.context_storage.semantic_search is False


def test_project_profile_renders_domain_block() -> None:
    from opencontext_core.config import ProjectConfig, ProjectProfile

    # Default profile is empty and renders nothing (section omitted entirely).
    assert ProjectConfig(name="x").profile.is_empty()
    assert ProjectProfile().to_context_block() == ""

    profile = ProjectProfile(
        purpose="Indexes code into a knowledge graph.",
        audience="AI coding agents.",
        problem="Agents relearn the project every session.",
        key_decisions=["MCP-first surface", "deterministic gates"],
    )
    block = profile.to_context_block()
    assert block.startswith("## Project Profile")
    assert "**Purpose:** Indexes code into a knowledge graph." in block
    assert "**Audience:** AI coding agents." in block
    assert "**Problem:** Agents relearn the project every session." in block
    assert "  - MCP-first surface" in block
    assert "  - deterministic gates" in block


def test_project_config_accepts_profile_via_validate() -> None:
    from opencontext_core.config import ProjectConfig

    cfg = ProjectConfig.model_validate(
        {"name": "demo", "profile": {"purpose": "p", "key_decisions": ["d1"]}}
    )
    assert cfg.profile.purpose == "p"
    assert cfg.profile.key_decisions == ["d1"]
    assert not cfg.profile.is_empty()

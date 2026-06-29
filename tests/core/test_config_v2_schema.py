"""PR-013 SPEC-CLI-013-01: opencontext.yaml v2 section envelope + v1 back-compat."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config import OpenContextConfig, default_config_data, load_config


def test_default_config_round_trips_as_v1() -> None:
    config = OpenContextConfig.model_validate(default_config_data())
    assert config.version == 1
    assert config.profile == "balanced"


def test_v2_file_loads_with_named_sections(tmp_path: Path) -> None:
    (tmp_path / "opencontext.yaml").write_text(
        "version: 2\n"
        "profile: enterprise\n"
        "project:\n  name: demo\n"
        "workflow:\n  default: sdd\n"
        "policies:\n  preset: restricted\n"
        "harnesses:\n  pytest: {}\n"
        "studio:\n  enabled: false\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path / "opencontext.yaml")
    assert config.version == 2
    assert config.workflow == {"default": "sdd"}
    assert config.policies == {"preset": "restricted"}
    assert config.harnesses == {"pytest": {}}
    assert config.studio == {"enabled": False}


def test_v1_file_without_version_loads_as_v1(tmp_path: Path) -> None:
    (tmp_path / "opencontext.yaml").write_text("project:\n  name: legacy\n", encoding="utf-8")
    config = load_config(tmp_path / "opencontext.yaml")
    assert config.version == 1


def test_studio_section_reserved_validates(tmp_path: Path) -> None:
    # SPEC-CLI-013-18: the studio section validates without a Studio impl.
    config = OpenContextConfig.model_validate(
        {**default_config_data(), "version": 2, "studio": {"layout": "grid"}}
    )
    assert config.studio == {"layout": "grid"}

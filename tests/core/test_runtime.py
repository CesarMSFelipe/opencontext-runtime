from __future__ import annotations

from pathlib import Path

import yaml

from conftest import create_sample_project, write_config
from opencontext_core.config import default_config_data
from opencontext_core.errors import ConfigurationError
from opencontext_core.runtime import OpenContextRuntime


def test_runtime_uses_safe_defaults_when_no_config_file_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    runtime = OpenContextRuntime(storage_path=tmp_path / ".storage/opencontext")

    assert runtime.config.models.default.provider == "mock"


def test_runtime_indexes_asks_and_persists_trace(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config_path = write_config(tmp_path, project_root)
    runtime = OpenContextRuntime(
        config_path=config_path,
        storage_path=tmp_path / ".storage/opencontext",
    )

    manifest = runtime.index_project(project_root)
    result = runtime.ask("Where is authentication implemented?")
    trace = runtime.latest_trace()

    assert len(manifest.files) == 2
    assert result.trace_id == trace.run_id
    assert result.selected_context_count > 0
    assert result.token_usage["selected_after_optimization"] <= 6500
    assert "Mock response generated" in result.answer
    assert any("retrieval_rationale" in item.metadata for item in trace.selected_context_items)


def test_runtime_sets_up_project_without_cli(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    config_path = write_config(tmp_path, project_root)
    runtime = OpenContextRuntime(
        config_path=config_path,
        storage_path=tmp_path / ".storage/opencontext",
    )

    result = runtime.setup_project(project_root)

    assert result.files == 3
    assert result.symbols > 0
    assert (project_root / "opencontext.yaml").exists()
    assert (project_root / ".opencontext/agents/README.md").exists()
    assert (project_root / ".opencontext/models/default.yaml").exists()
    assert runtime.load_manifest().root == str(project_root.resolve())


def test_air_gapped_mode_blocks_external_capabilities(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    create_sample_project(project_root)
    data = default_config_data()
    data["project_index"]["root"] = str(project_root)
    data["security"]["mode"] = "air_gapped"
    data["security"]["external_providers_enabled"] = True
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    try:
        OpenContextRuntime(config_path=config_path, storage_path=tmp_path / ".storage/opencontext")
    except ConfigurationError as exc:
        assert "air_gapped mode forbids external providers" in str(exc)
    else:
        raise AssertionError("air_gapped runtime must reject external providers")

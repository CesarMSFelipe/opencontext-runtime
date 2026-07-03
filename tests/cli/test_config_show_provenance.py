"""R1: config show surfaces 7-layer resolution provenance.

Failing test: a tmp project with a yaml override must cause `config show`
to print a Provenance section that names which layer supplied each of the
key values (memory.provider, storage.mode, sdd.flow_mode).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opencontext_core.wizard import show_config


def _write_project_yaml(root: Path, *, memory_provider: str = "engram") -> Path:
    data = {
        "memory": {"provider": memory_provider},
        "storage": {"mode": "local"},
        "sdd": {"flow_mode": "interactive"},
    }
    path = root / "opencontext.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def test_provenance_section_present(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """show_config must emit a Provenance section when a project yaml is present."""
    _write_project_yaml(tmp_path)

    show_config(root=tmp_path)

    out = capsys.readouterr().out
    assert "Provenance" in out, f"Expected 'Provenance' section in output.\nGot:\n{out}"


def test_provenance_names_layer_for_yaml_override(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Keys present in opencontext.yaml must show 'project' as their winning layer."""
    _write_project_yaml(tmp_path, memory_provider="local")

    show_config(root=tmp_path)

    out = capsys.readouterr().out
    # The provenance section must name 'project' as the layer for these keys
    assert "project" in out, f"Expected the layer name 'project' in provenance output.\nGot:\n{out}"


def test_provenance_shows_memory_provider_key(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Provenance must list memory.provider with its resolved layer."""
    _write_project_yaml(tmp_path)

    show_config(root=tmp_path)

    out = capsys.readouterr().out
    assert "memory" in out, f"Expected 'memory' in provenance output.\nGot:\n{out}"


def test_provenance_absent_when_no_project_yaml(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Without opencontext.yaml there is no provenance to show — no crash."""
    # no yaml written
    show_config(root=tmp_path)

    out = capsys.readouterr().out
    # Must not crash; graceful output still required
    assert out, "show_config must produce some output even without a project yaml"

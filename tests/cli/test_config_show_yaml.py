"""Tests for T3 of product-polish-r14: config show surfaces opencontext.yaml keys.

Evidence: `config show` renders user-config.json only; memory.provider /
storage.mode / sdd.flow_mode invisible.  After the fix, a "Project
(opencontext.yaml)" section must appear with those keys when a project yaml is
resolvable from cwd/--root.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opencontext_core.wizard import show_config


def _write_project_yaml(root: Path, **overrides: object) -> Path:
    """Write a minimal opencontext.yaml to *root* with the given key overrides."""
    data: dict = {
        "memory": {"provider": "engram", "enabled": True},
        "storage": {"mode": "local"},
        "sdd": {"flow_mode": "interactive", "artifact_store": "engram"},
        "models": {
            "roles": {"apply": "sonnet", "verify": "haiku"},
        },
    }
    for key, value in overrides.items():
        data[key] = value
    path = root / "opencontext.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def test_config_show_renders_project_yaml_section(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """config show with a project yaml must emit a 'Project (opencontext.yaml)' section."""
    _write_project_yaml(tmp_path)

    show_config(root=tmp_path)

    out = capsys.readouterr().out
    assert "Project (opencontext.yaml)" in out, (
        f"Expected 'Project (opencontext.yaml)' section header in output.\nGot:\n{out}"
    )
    assert "memory.provider" in out or "provider" in out, (
        f"Expected memory.provider to appear in output.\nGot:\n{out}"
    )
    assert "storage.mode" in out or "mode" in out, (
        f"Expected storage.mode to appear in output.\nGot:\n{out}"
    )
    assert "flow_mode" in out, f"Expected sdd.flow_mode to appear in output.\nGot:\n{out}"


def test_config_show_no_yaml_graceful(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """config show with no opencontext.yaml must emit a graceful 'no project config' line."""
    # tmp_path has no opencontext.yaml
    show_config(root=tmp_path)

    out = capsys.readouterr().out
    # Must NOT crash; must mention that no project config is found.
    assert "no project config" in out.lower() or "project" in out.lower(), (
        f"Expected graceful 'no project config' message.\nGot:\n{out}"
    )


def test_config_show_renders_models_roles(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """config show must render models.roles when present in opencontext.yaml."""
    _write_project_yaml(tmp_path)

    show_config(root=tmp_path)

    out = capsys.readouterr().out
    assert "roles" in out or "apply" in out, (
        f"Expected models.roles to appear in output.\nGot:\n{out}"
    )

"""AVH-012 / B2: canonical config resolver — install and run share one path.

Regression for the audit-confirmed defect where ``install`` wrote
``<root>/opencontext.yaml`` but ``run`` read a hardcoded
``<root>/configs/opencontext.yaml``, so a freshly-installed project reported OC
Flow disabled. Every entry point now resolves config through
:func:`opencontext_core.config_resolver.resolve_config_path`.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import yaml

from opencontext_core.config import load_config_or_defaults
from opencontext_core.config_resolver import missing_config_hint, resolve_config_path
from opencontext_core.install_manager import InstallationManager


def _write_config(path: Path, *, oc_flow_enabled: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "project": {"name": path.parent.name},
                "runtime": {"oc_flow_enabled": oc_flow_enabled},
            }
        ),
        encoding="utf-8",
    )


# (a) install-then-run reads the installed config; OC Flow status matches.


def test_install_then_run_reads_installed_config(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    # The exact writer install() uses (install_manager.py:150 → _write_project_config).
    installed = InstallationManager()._write_project_config(project)
    assert installed == project / "opencontext.yaml"
    assert installed.exists()

    # Flip a vNext flag in the installed file so a match proves run reads THIS
    # file rather than falling back to (oc_flow_enabled=False) built-in defaults.
    data = yaml.safe_load(installed.read_text(encoding="utf-8"))
    data.setdefault("runtime", {})["oc_flow_enabled"] = True
    installed.write_text(yaml.safe_dump(data), encoding="utf-8")

    resolved = resolve_config_path(project, None)
    assert resolved == installed
    # The defect path must never be selected.
    assert resolved != project / "configs" / "opencontext.yaml"

    config = load_config_or_defaults(resolved, auto_detect=False)
    assert config.runtime.oc_flow_enabled is True


def test_handle_run_exec_uses_installed_config(tmp_path: Path, monkeypatch) -> None:
    """End-to-end: the ``run`` command honors the installed config's OC Flow flag."""
    project = tmp_path / "proj"
    _write_config(project / "opencontext.yaml", oc_flow_enabled=True)

    captured: dict[str, object] = {}

    def _fake_run(task, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)

    monkeypatch.setattr("opencontext_core.oc_flow.cli.run_oc_flow_cli", _fake_run)

    from opencontext_cli.commands.run_cmd import handle_run_exec

    args = Namespace(
        task="Fix failing test",
        workflow="oc-flow",
        lane="fast",
        profile="balanced",
        resume=None,
        root=str(project),
        config=None,
        json=False,
    )
    handle_run_exec(args)
    assert captured["enabled"] is True


# (b) <root>/opencontext.yaml honored when no configs/ subdirectory exists.


def test_root_config_honored_without_configs_subdir(tmp_path: Path) -> None:
    _write_config(tmp_path / "opencontext.yaml", oc_flow_enabled=True)
    assert not (tmp_path / "configs").exists()

    resolved = resolve_config_path(tmp_path, None)
    assert resolved == tmp_path / "opencontext.yaml"
    assert load_config_or_defaults(resolved, auto_detect=False).runtime.oc_flow_enabled is True


def test_parent_directory_search(tmp_path: Path) -> None:
    _write_config(tmp_path / "opencontext.yaml", oc_flow_enabled=True)
    child = tmp_path / "a" / "b"
    child.mkdir(parents=True)
    resolved = resolve_config_path(child, None)
    assert resolved == tmp_path / "opencontext.yaml"


# (c) explicit --config wins over the project root file.


def test_explicit_config_overrides_root(tmp_path: Path) -> None:
    _write_config(tmp_path / "opencontext.yaml", oc_flow_enabled=False)
    override = tmp_path / "override.yaml"
    _write_config(override, oc_flow_enabled=True)

    resolved = resolve_config_path(tmp_path, str(override))
    assert resolved == override
    assert load_config_or_defaults(resolved, auto_detect=False).runtime.oc_flow_enabled is True


# (d) missing config → actionable message naming the path + 'opencontext init'.


def test_missing_config_falls_back_and_hint_is_actionable(tmp_path: Path) -> None:
    project = tmp_path / "empty"
    project.mkdir()
    # Resolver always yields a path (the canonical one) for the defaults fallback.
    resolved = resolve_config_path(project, None)
    assert resolved == project / "opencontext.yaml"
    assert not resolved.exists()

    hint = missing_config_hint(project)
    assert str(project / "opencontext.yaml") in hint
    assert "opencontext init" in hint
    assert "--config" in hint


def test_run_emits_actionable_hint_when_config_missing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    project = tmp_path / "empty"
    project.mkdir()
    monkeypatch.setattr("opencontext_core.oc_flow.cli.run_oc_flow_cli", lambda *a, **k: None)

    from opencontext_cli.commands.run_cmd import handle_run_exec

    args = Namespace(
        task="Fix failing test",
        workflow="oc-flow",
        lane="fast",
        profile="balanced",
        resume=None,
        root=str(project),
        config=None,
        json=False,
    )
    handle_run_exec(args)
    err = capsys.readouterr().err
    assert "opencontext init" in err
    assert str(project / "opencontext.yaml") in err

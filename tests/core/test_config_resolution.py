"""PR-013 SPEC-CLI-013-03: seven-level configuration resolution + provenance."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config_resolver import LAYERS, resolve


def _write(root: Path, body: str) -> None:
    (root / "opencontext.yaml").write_text(body, encoding="utf-8")


def test_layers_are_ordered() -> None:
    assert LAYERS == (
        "defaults",
        "profile",
        "global",
        "project",
        "env",
        "overrides",
        "policy",
    )


def test_env_var_overrides_project_profile(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nprofile: balanced\nproject:\n  name: demo\n")
    resolved = resolve(tmp_path, env={"OPENCONTEXT_PROFILE": "low-cost"}, global_config={})
    assert resolved.profile == "low-cost"
    assert resolved.provenance.profile_layer == "env"
    # low-cost overlay routes providers to cheapest.
    assert resolved.config.providers.strategy == "cheapest"


def test_project_profile_used_when_no_env(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nprofile: balanced\nproject:\n  name: demo\n")
    resolved = resolve(tmp_path, env={}, global_config={})
    assert resolved.profile == "balanced"
    assert resolved.provenance.profile_layer == "project"


def test_provenance_records_winning_layer(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nproject:\n  name: demo\n")
    resolved = resolve(
        tmp_path,
        env={},
        global_config={},
        cli_overrides={"ui_language": "es"},
    )
    assert resolved.provenance.layer_of("ui_language") == "overrides"
    assert resolved.config.ui_language == "es"


def test_cli_override_beats_project(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nprofile: balanced\nproject:\n  name: demo\n")
    resolved = resolve(
        tmp_path, env={}, global_config={}, cli_overrides={"profile": "performance"}
    )
    assert resolved.profile == "performance"
    assert resolved.provenance.profile_layer == "overrides"

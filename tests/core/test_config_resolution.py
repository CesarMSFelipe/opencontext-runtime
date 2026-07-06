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
    resolved = resolve(tmp_path, env={}, global_config={}, cli_overrides={"profile": "performance"})
    assert resolved.profile == "performance"
    assert resolved.provenance.profile_layer == "overrides"


# ── CFG-001..003: precedence at the resolver level ─────────────────────────


def test_project_beats_global(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nproject:\n  name: demo\nui_language: es\n")
    resolved = resolve(tmp_path, env={}, global_config={"ui_language": "en"})
    assert resolved.config.ui_language == "es"
    assert resolved.provenance.dotted_layer_of("ui_language") == "project"


def test_env_beats_project(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nproject:\n  name: demo\nsecurity:\n  mode: private_project\n")
    resolved = resolve(tmp_path, env={"OPENCONTEXT_SECURITY_MODE": "enterprise"}, global_config={})
    assert resolved.config.security.mode.value == "enterprise"
    assert resolved.provenance.dotted_layer_of("security.mode") == "env"


def test_cli_flag_beats_env(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nproject:\n  name: demo\n")
    resolved = resolve(
        tmp_path,
        env={"OPENCONTEXT_UI_LANGUAGE": "es"},
        global_config={},
        cli_overrides={"ui_language": "en"},
    )
    assert resolved.config.ui_language == "en"
    assert resolved.provenance.dotted_layer_of("ui_language") == "overrides"


# ── Nested dotted-key provenance (config explain substrate) ────────────────


def test_dotted_provenance_tracks_nested_keys(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nproject:\n  name: demo\nharness:\n  tdd_mode: strict\n")
    resolved = resolve(tmp_path, env={}, global_config={})
    assert resolved.provenance.dotted_layer_of("harness.tdd_mode") == "project"
    # A key no layer set resolves to defaults.
    assert resolved.provenance.dotted_layer_of("harness.strict_tdd") == "defaults"
    # Both defaults and project set project.name, in merge order.
    layers = resolved.provenance.dotted_key_layers["project.name"]
    assert layers.index("defaults") < layers.index("project")


# ── CFG-004: the ci profile disables interactivity through the resolver ─────


def test_ci_profile_disables_interactivity_via_resolver(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nprofile: ci\nproject:\n  name: demo\n")
    resolved = resolve(tmp_path, env={}, global_config={})
    assert resolved.profile == "ci"
    assert resolved.config.interface.interactive is False
    assert resolved.config.interface.tui is False
    assert resolved.config.interface.json_default is True
    assert resolved.provenance.dotted_layer_of("interface.interactive") == "profile"


# ── Canonical env map covers the ad-hoc env vars ────────────────────────────


def test_env_map_covers_tdd_and_storage_mode(tmp_path: Path) -> None:
    _write(tmp_path, "version: 2\nproject:\n  name: demo\n")
    resolved = resolve(
        tmp_path,
        env={"OPENCONTEXT_TDD_MODE": "strict", "OPENCONTEXT_STORAGE_MODE": "local"},
        global_config={},
    )
    assert resolved.config.harness.tdd_mode == "strict"
    assert resolved.config.storage.mode.value == "local"
    assert resolved.provenance.dotted_layer_of("harness.tdd_mode") == "env"
    assert resolved.provenance.dotted_layer_of("storage.mode") == "env"


# ── CFG-010: resolver TDD value reaches the harness config read ─────────────


def test_tdd_mode_propagates_to_harness_governance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENCONTEXT_TDD_MODE", raising=False)
    _write(tmp_path, "version: 2\nproject:\n  name: demo\nharness:\n  tdd_mode: strict\n")
    resolved = resolve(tmp_path, env={}, global_config={})
    assert resolved.config.harness.tdd_mode == "strict"

    from types import SimpleNamespace

    from opencontext_core.harness.runner import HarnessRunner

    class _Stub:
        _harness_governance = HarnessRunner._harness_governance

    stub = _Stub()
    stub.root = tmp_path
    stub.config = SimpleNamespace(tdd_mode="ask", approval_required_for_writes=False)
    tdd_mode, _approval = stub._harness_governance()
    assert tdd_mode == "strict"

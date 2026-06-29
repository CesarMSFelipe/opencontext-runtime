"""Read-only dual-run flag catalog (SPEC CL-005/010)."""

from __future__ import annotations

from opencontext_core.compat import MigrationState, flag_catalog, flag_spec
from opencontext_core.config import RuntimeMigrationConfig


def test_catalog_covers_the_runtime_flags() -> None:
    names = {s.name for s in flag_catalog()}
    expected = {
        "runtime.session_wrapper",
        "runtime.registry_enabled",
        "runtime.persona_registry_enabled",
        "runtime.skill_registry_enabled",
        "runtime.harness_registry_enabled",
        "runtime.gateway_enabled",
        "runtime.context_engine_enabled",
        "runtime.execution_profile",
        "runtime.durable_artifacts",
        "runtime.sdd_strict",
        "runtime.oc_flow_enabled",
        "runtime_brain.enabled",
    }
    assert expected.issubset(names)


def test_catalog_includes_vnext_subsystem_flags() -> None:
    # AVH-003: the four previously-missing vNext flags must be catalogued, each with
    # a mapped subsystem (not "(unmapped)") and a migration_state (migration-visible).
    by_name = {s.name: s for s in flag_catalog()}
    for name, subsystem in {
        "runtime.kg_v2_enabled": "knowledge_graph",
        "runtime.memory_v2_enabled": "memory",
        "runtime_intelligence_enabled": "runtime_intelligence",
        "learning.loop.enabled": "learning_loop",
    }.items():
        spec = by_name.get(name)
        assert spec is not None, f"{name} missing from flag_catalog()"
        assert spec.subsystem == subsystem
        assert spec.migration_state in set(MigrationState)
        assert spec.default is False


def test_session_wrapper_defaults_on() -> None:
    spec = flag_spec("runtime.session_wrapper")
    assert spec is not None
    assert spec.default is True
    assert spec.is_legacy_default is True  # CL-010: off route is the legacy path


def test_every_enabled_flag_defaults_legacy() -> None:
    # CL-005: every *_enabled migration flag defaults False (legacy).
    for spec in flag_catalog():
        if spec.field.endswith("_enabled"):
            assert spec.default is False, spec.name
            assert spec.is_legacy_default is True


def test_catalog_fields_are_real_config_fields() -> None:
    config_fields = set(RuntimeMigrationConfig.model_fields)
    for spec in flag_catalog():
        if spec.name.startswith("runtime."):
            assert spec.field in config_fields, spec.name


def test_pending_subsystems_report_legacy_state() -> None:
    assert flag_spec("runtime.gateway_enabled").migration_state is MigrationState.legacy
    assert flag_spec("runtime.context_engine_enabled").migration_state is MigrationState.legacy
    assert flag_spec("runtime.registry_enabled").migration_state is MigrationState.adapted


def test_one_flip_is_isolated() -> None:
    # CL-005: flipping registry_enabled leaves gateway/context flags legacy.
    cfg = RuntimeMigrationConfig(registry_enabled=True)
    assert cfg.registry_enabled is True
    assert cfg.gateway_enabled is False
    assert cfg.context_engine_enabled is False


def test_retention_nested_block_is_not_a_flag() -> None:
    # Nested config models must not leak into the flag catalog.
    assert "runtime.retention" not in {s.name for s in flag_catalog()}

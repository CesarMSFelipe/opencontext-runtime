"""Read-only dual-run flag catalog (SPEC CL-005/010)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.compat import MigrationState, flag_catalog, flag_spec
from opencontext_core.compat.flags import FlagSpec
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
    # CL-005 (ledger-driven): a subsystem with an ACCEPTED flip-evidence bundle is EXEMPT
    # from the default-False assertion (its vNext default is recorded migration evidence);
    # an un-migrated flag must still default legacy-off.
    accepted = _accepted_subsystems(Path(__file__).resolve().parents[2])
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
        if subsystem not in accepted:
            assert spec.default is False


def test_session_wrapper_defaults_on() -> None:
    spec = flag_spec("runtime.session_wrapper")
    assert spec is not None
    assert spec.default is True
    assert spec.is_legacy_default is True  # CL-010: off route is the legacy path


def _assert_enabled_flags_legacy_unless_flipped(
    accepted: set[str], *, catalog: list[FlagSpec] | None = None
) -> None:
    """CL-005 core check (ledger-driven).

    Every ``*_enabled`` migration flag MUST default to the legacy path (``False``)
    UNLESS its subsystem carries an ACCEPTED flip-evidence bundle. An accepted bundle is
    the recorded, parity-gated migration evidence, so that subsystem's flags are EXEMPT
    from the default-False assertion; every other ``*_enabled`` flag is still enforced.
    """
    for spec in catalog if catalog is not None else flag_catalog():
        if spec.field.endswith("_enabled"):
            if spec.subsystem in accepted:
                continue  # accepted flip bundle = recorded migration evidence
            assert spec.default is False, spec.name
            assert spec.is_legacy_default is True


def _accepted_subsystems(root: Path) -> set[str]:
    """Subsystems whose committed/runtime flip bundle is ACCEPTED (migration evidence)."""
    from opencontext_core.compat.flip_evidence import read_flip_bundles

    return {bundle.subsystem for bundle in read_flip_bundles(root) if bundle.accepted}


def _enabled_spec(field: str, subsystem: str, *, default: bool) -> FlagSpec:
    """A synthetic ``*_enabled`` flag spec for the exemption test."""
    return FlagSpec(
        name=f"runtime.{field}",
        field=field,
        subsystem=subsystem,
        default=default,
        migration_state=MigrationState.legacy,
        superseding_pr="PR-TEST",
        note="synthetic spec for the CL-005 exemption test",
    )


def test_every_enabled_flag_defaults_legacy_unless_flipped() -> None:
    # CL-005 (ledger/flip-bundle driven): every *_enabled migration flag defaults False
    # (legacy) UNLESS its subsystem has an ACCEPTED flip-evidence bundle. On a fresh
    # checkout there are no accepted bundles, so read_flip_bundles() -> [] and every flag
    # is asserted legacy-default (the test passes, it never errors).
    repo = Path(__file__).resolve().parents[2]
    _assert_enabled_flags_legacy_unless_flipped(_accepted_subsystems(repo))


def test_fresh_checkout_has_no_accepted_bundles_enforces_legacy(tmp_path: Path) -> None:
    # VDM-001/002 fresh-checkout safety: with neither a committed baseline nor the runtime
    # flips dir present, read_flip_bundles() returns [] and CL-005 enforcement is ACTIVE —
    # a flag defaulting vNext with no accepted bundle must fail. Uses a synthetic spec so it
    # tests the mechanism independently of the real (now partially-migrated) config defaults.
    from opencontext_core.compat.flip_evidence import read_flip_bundles

    assert read_flip_bundles(tmp_path) == []
    rogue = _enabled_spec("kg_v2_enabled", "knowledge_graph", default=True)
    with pytest.raises(AssertionError):
        _assert_enabled_flags_legacy_unless_flipped(
            _accepted_subsystems(tmp_path), catalog=[rogue]
        )


def test_accepted_bundle_exempts_its_subsystem_only() -> None:
    # An accepted flip bundle exempts ONLY its own subsystem from the default-False
    # assertion; every other *_enabled flag must still default legacy. Uses synthetic
    # flipped-ON specs so the exemption is actually exercised (real defaults stay False
    # this phase, which would make a no-op assertion).
    flipped = _enabled_spec("oc_flow_enabled", "oc_flow", default=True)
    not_flipped = _enabled_spec("kg_v2_enabled", "knowledge_graph", default=True)
    catalog = [flipped, not_flipped]

    # only oc_flow accepted -> knowledge_graph (default True, no bundle) MUST fail.
    with pytest.raises(AssertionError):
        _assert_enabled_flags_legacy_unless_flipped({"oc_flow"}, catalog=catalog)

    # both accepted -> both exempt -> no assertion error.
    _assert_enabled_flags_legacy_unless_flipped({"oc_flow", "knowledge_graph"}, catalog=catalog)

    # none accepted -> the flipped-on flag is enforced and fails (regression guard intact).
    with pytest.raises(AssertionError):
        _assert_enabled_flags_legacy_unless_flipped(set(), catalog=catalog)


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
    # CL-005 (ledger-driven): setting ONE flag explicitly must not cascade — every other
    # flag keeps its LIVE field default. A subsystem WITHOUT an accepted flip bundle must
    # still default legacy-off (regression guard intact); a flipped subsystem (accepted
    # bundle) is exempt and legitimately keeps its vNext default.
    accepted = _accepted_subsystems(Path(__file__).resolve().parents[2])
    cfg = RuntimeMigrationConfig(registry_enabled=True)
    assert cfg.registry_enabled is True
    fields = RuntimeMigrationConfig.model_fields
    for field, subsystem in (
        ("gateway_enabled", "provider_gateway"),
        ("context_engine_enabled", "context_engine"),
    ):
        live_default = fields[field].default
        assert getattr(cfg, field) == live_default  # no cascade from the registry flip
        if subsystem not in accepted:
            assert live_default is False


def test_retention_nested_block_is_not_a_flag() -> None:
    # Nested config models must not leak into the flag catalog.
    assert "runtime.retention" not in {s.name for s in flag_catalog()}

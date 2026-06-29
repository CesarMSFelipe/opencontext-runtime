"""PR-015 SDK conformance suite tests (doc 60 item 14, PLG-CONV)."""

from __future__ import annotations

from opencontext_core.plugins.conformance import run_conformance
from opencontext_core.plugins.manifest import PluginManifest


def _manifest(**overrides: object) -> PluginManifest:
    base: dict = {
        "schema_version": "opencontext.plugin.v1",
        "id": "opencontext.demo",
        "name": "Demo",
        "version": "1.0.0",
        "entrypoint": "plugin.py",
        "requires": {"runtime": ">=1.0"},
        "contributes": {"personas": ["oc-demo-engineer"]},
    }
    base.update(overrides)
    return PluginManifest.model_validate(base)


def test_well_formed_plugin_passes_conformance() -> None:
    report = run_conformance(_manifest(), core_version="1.5.0")
    assert report.passed, report.failures
    assert {c.id for c in report.checks} >= {"CONF-1", "CONF-2", "CONF-3", "CONF-4", "CONF-5"}


def test_missing_id_fails_conformance() -> None:
    report = run_conformance(_manifest(id=None))
    assert not report.passed
    assert any(c.id == "CONF-2" and not c.passed for c in report.failures)


def test_wrong_schema_version_fails() -> None:
    report = run_conformance(_manifest(schema_version="opencontext.plugin.v2"))
    assert any(c.id == "CONF-1" and not c.passed for c in report.failures)


def test_incompatible_plugin_fails_conf6() -> None:
    report = run_conformance(_manifest(requires={"runtime": ">=99.0"}), core_version="1.5.0")
    assert any(c.id == "CONF-6" and not c.passed for c in report.failures)


def test_panel_only_plugin_with_mutation_perms_fails() -> None:
    """PLG-CONV: a Studio-panel-only plugin must declare no mutation permission."""
    report = run_conformance(
        _manifest(
            contributes={"studio_panels": ["my-panel"]},
            permissions={"kg_write": ["*"]},
        )
    )
    assert any(c.id == "CONF-4" and not c.passed for c in report.failures)


def test_panel_plus_provider_may_declare_mutation_perms() -> None:
    """A plugin that also contributes a KG provider legitimately needs kg_write."""
    report = run_conformance(
        _manifest(
            contributes={"studio_panels": ["my-panel"], "kg_providers": ["my-kg"]},
            permissions={"kg_write": ["*"]},
        ),
        core_version="1.5.0",
    )
    conf4 = next(c for c in report.checks if c.id == "CONF-4")
    assert conf4.passed


def test_conformance_covers_conv_points() -> None:
    """PLG-CONV: execution-profile / cache-provider contributions are conformant."""
    report = run_conformance(
        _manifest(contributes={"execution_profiles": ["fast"], "cache_providers": ["redis"]}),
        core_version="1.5.0",
    )
    assert report.passed, report.failures

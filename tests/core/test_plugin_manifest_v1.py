"""PR-015 manifest + contracts tests (AC-MF1/MF2/PM2/CT1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.plugins.contracts import CONTRACTS
from opencontext_core.plugins.contracts import __all__ as PUBLIC_SURFACE
from opencontext_core.plugins.extension_points import (
    CONTRIBUTION_ROUTES,
    ExtensionPoint,
)
from opencontext_core.plugins.manifest import (
    PLUGIN_SCHEMA_VERSION,
    PluginContributions,
    PluginManifest,
    PluginPermissions,
)


def test_manifest_exposes_typed_contract_fields() -> None:
    """AC-MF1: a book-shaped manifest exposes schema_version/id/requires/contributes."""
    m = PluginManifest.model_validate(
        {
            "schema_version": "opencontext.plugin.v1",
            "id": "opencontext.demo",
            "name": "Demo",
            "version": "1.0.0",
            "entrypoint": "plugin.py",
            "requires": {"runtime": ">=1.0", "api": "v1"},
            "contributes": {"personas": ["oc-drupal-engineer"]},
        }
    )
    assert m.schema_version == PLUGIN_SCHEMA_VERSION
    assert m.id == "opencontext.demo"
    assert m.requires.runtime == ">=1.0"
    assert m.contributes.personas == ["oc-drupal-engineer"]


def test_legacy_plugin_json_still_validates() -> None:
    """AC-MF1: an on-disk plugin.json (no schema_version/contributes) validates."""
    m = PluginManifest.from_plugin_json(
        {
            "name": "legacy",
            "version": "0.1.0",
            "entry_point": "plugin.py",
            "enabled": True,
            "hooks": [],
            "author": "someone",
            "installed_at": "2026-01-01",
            "permissions": {},
        }
    )
    assert m.entrypoint == "plugin.py"
    assert m.requires.runtime == ">=0.1"  # defaulted
    assert m.contributes.is_empty()


def test_all_fifteen_plus_extension_points_addressable() -> None:
    """AC-MF2: every extension point is present as a (possibly empty) list."""
    c = PluginContributions()
    expected = {
        "workflows",
        "personas",
        "skills",
        "harnesses",
        "policies",
        "providers",
        "kg_providers",
        "memory_providers",
        "context_strategies",
        "runtime_intelligence_analyzers",
        "studio_panels",
        "cli_commands",
        "mcp_tools",
        "project_templates",
        "benchmark_suites",
        # PLG-CONV additions
        "execution_profiles",
        "cache_providers",
    }
    assert set(type(c).model_fields) == expected
    for field_name in expected:
        assert getattr(c, field_name) == []


def test_persona_contribution_round_trips() -> None:
    """AC-MF2: a declared persona contribution is readable."""
    c = PluginContributions(personas=["oc-drupal-engineer"])
    assert c.personas == ["oc-drupal-engineer"]
    assert c.items() == [("personas", ["oc-drupal-engineer"])]


def test_full_permission_set_deny_by_default() -> None:
    """AC-PM2: the full capability set defaults empty (deny-by-default)."""
    p = PluginPermissions()
    for cap in ("read_paths", "write_paths", "network_hosts", "mcp_servers"):
        assert getattr(p, cap) == []
    for cap in ("command", "provider", "kg_write", "memory_write"):
        assert getattr(p, cap) == []


def test_unknown_contribution_point_rejected() -> None:
    """contributes is extra='forbid' — an unknown point is a manifest error."""
    with pytest.raises(ValidationError):
        PluginContributions.model_validate({"not_a_point": ["x"]})


def test_every_extension_point_has_a_contract_route() -> None:
    """AC-CT1: each of the 17 points routes to a public contract."""
    assert len(list(ExtensionPoint)) == 17
    assert set(CONTRIBUTION_ROUTES) == set(ExtensionPoint)
    for point in ExtensionPoint:
        route = CONTRIBUTION_ROUTES[point]
        assert route.contract in CONTRACTS


def test_contracts_reuse_existing_types_not_redefined() -> None:
    """AC-CT1: memory/provider/cache contracts alias the existing in-tree types."""
    from opencontext_core.cache.base import ResponseCache as CacheResponseCache
    from opencontext_core.memory.provider import MemoryProvider as RealMemoryProvider
    from opencontext_core.plugins.contracts import MemoryProvider, ProviderAdapter, ResponseCache
    from opencontext_core.providers.adapters import ProviderAdapter as RealProviderAdapter

    assert MemoryProvider is RealMemoryProvider
    assert ProviderAdapter is RealProviderAdapter
    assert ResponseCache is CacheResponseCache


def test_public_surface_exports_no_private_names() -> None:
    """AC-CT1: nothing in __all__ is a private (underscore) name."""
    assert PUBLIC_SURFACE  # non-empty
    assert all(not name.startswith("_") for name in PUBLIC_SURFACE)

"""PR-006 registry contract guards: versions, shared base, plugin metadata.

The three registries share one base (``Registry[T]``) and one provenance metadata
model. These tests pin the internal contract versions (doc 59) and prove the base
API behaves identically across registries.
"""

from __future__ import annotations

import pytest

from opencontext_core.harness.definition import (
    HARNESS_CONTRACT_VERSION,
    HARNESS_SCHEMA_VERSION,
)
from opencontext_core.personas.definition import (
    PERSONA_CONTRACT_VERSION,
    PERSONA_SCHEMA_VERSION,
    PersonaDefinition,
)
from opencontext_core.registries.base import (
    DuplicateDefinition,
    Registry,
    RegistryMetadata,
    RegistryNotFound,
    RegistrySource,
    TrustLevel,
)
from opencontext_core.skills.definition import (
    SKILL_CONTRACT_VERSION,
    SKILL_SCHEMA_VERSION,
)


def test_internal_contract_versions_are_one() -> None:
    assert PERSONA_CONTRACT_VERSION == 1
    assert SKILL_CONTRACT_VERSION == 1
    assert HARNESS_CONTRACT_VERSION == 1


def test_schema_versions_are_v1_family() -> None:
    assert PERSONA_SCHEMA_VERSION == "opencontext.persona.v1"
    assert SKILL_SCHEMA_VERSION == "opencontext.skill.v1"
    assert HARNESS_SCHEMA_VERSION == "opencontext.harness.v1"


def test_shared_base_register_get_list_raise() -> None:
    reg: Registry[PersonaDefinition] = Registry()
    reg.kind = "thing"
    a = PersonaDefinition(id="a")
    reg.register(a)
    assert reg.get("a") is a
    assert reg.has("a") is True
    assert reg.list_ids() == ["a"]
    assert len(reg) == 1
    with pytest.raises(RegistryNotFound):
        reg.get("missing")


def test_shared_base_rejects_silent_overwrite() -> None:
    reg: Registry[PersonaDefinition] = Registry()
    reg.register(PersonaDefinition(id="a", name="first"))
    with pytest.raises(DuplicateDefinition):
        reg.register(PersonaDefinition(id="a", name="second"))
    # replace=True is explicit and allowed.
    reg.register(PersonaDefinition(id="a", name="second"), replace=True)
    assert reg.get("a").name == "second"


def test_plugin_ready_metadata_defaults_to_trusted_builtin() -> None:
    meta = RegistryMetadata()
    assert meta.source == RegistrySource.BUILTIN
    assert meta.trust == TrustLevel.TRUSTED
    assert meta.permissions == []
    plugin = RegistryMetadata(
        source=RegistrySource.PLUGIN, trust=TrustLevel.UNTRUSTED, plugin_id="acme"
    )
    assert plugin.source == "plugin"
    assert plugin.trust == "untrusted"
    assert plugin.plugin_id == "acme"

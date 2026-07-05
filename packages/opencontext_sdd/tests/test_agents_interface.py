"""Tests for opencontext_sdd.agents.interface (Adapter Protocol + dedupe).

T1.21 -- ``test_adapter_protocol_required_methods_and_registry_rejects_dupes``
written FIRST; fails until T1.23 (Protocol) + T1.25 (registry) land.
"""

from __future__ import annotations

import pytest
from opencontext_sdd.agents import registry
from opencontext_sdd.agents.interface import Adapter


def test_adapter_protocol_required_methods_and_registry_rejects_dupes() -> None:
    """Adapter Protocol exposes the required methods and ADAPTERS is dedupe-safe."""
    required = (
        "id",
        "display_name",
        "config_paths",
        "install",
        "uninstall",
        "status",
        "sync_state",
        "apply",
        "verify",
    )
    for name in required:
        assert hasattr(Adapter, name), f"Adapter.{name} is required"

    for name, cls in registry.ADAPTERS.items():
        assert isinstance(name, str) and name, "registry keys must be non-empty strings"
        assert isinstance(cls, type), f"{name!r} must map to a class"
        assert issubclass(cls, Adapter) or hasattr(cls, "id"), (
            f"{cls.__name__} must implement the Adapter protocol"
        )

    keys = list(registry.ADAPTERS)
    assert len(keys) == len(set(keys)), "ADAPTERS must not contain duplicate names"

    # Building a duplicate via a fresh registry raises a clear error.
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(cls=type("Dup", (object,), {"id": "dup"}), name=keys[0])

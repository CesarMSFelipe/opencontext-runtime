"""Executor registry contract (plan doc 2 §14, EXE tests).

The registry formalizes what was previously hardcoded resolution: every
executor the runtime can attach (``none``, ``provider``, ``mcp``,
``test_stub``, ``patch``) is declared with honest capability flags, and the
resolution paths consult the registry instead of ad-hoc constructors.
EXE-001: an executor whose spec declares ``can_mutate=False`` can never
produce a mutation — the run reports ``needs_executor`` and no file changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.executors.registry import (
    ExecutorRegistry,
    ExecutorSpec,
    default_registry,
)


# ------------------------------------------------------------------ spec contract
def test_spec_defaults_are_least_capability() -> None:
    spec = ExecutorSpec(id="x")
    assert spec.can_mutate is False
    assert spec.can_run_commands is False
    assert spec.requires_network is False
    assert spec.requires_approval is False
    assert spec.supported_tasks == ()
    assert spec.supported_languages == ("*",)


def test_spec_to_dict_is_json_shaped() -> None:
    spec = ExecutorSpec(id="x", can_mutate=True, supported_tasks=("mutation",))
    data = spec.to_dict()
    assert data["id"] == "x"
    assert data["can_mutate"] is True
    assert data["supported_tasks"] == ["mutation"]
    assert data["supported_languages"] == ["*"]


# ------------------------------------------------------------- register/get/list
def test_register_get_list_roundtrip() -> None:
    registry = ExecutorRegistry()
    spec = ExecutorSpec(id="demo", can_mutate=True)
    registry.register(spec)
    assert registry.get("demo") is spec
    assert registry.get("missing") is None
    assert [s.id for s in registry.list()] == ["demo"]


def test_register_duplicate_id_rejected() -> None:
    registry = ExecutorRegistry()
    registry.register(ExecutorSpec(id="demo"))
    with pytest.raises(ValueError):
        registry.register(ExecutorSpec(id="demo"))


def test_build_unknown_id_raises_key_error(tmp_path: Path) -> None:
    registry = ExecutorRegistry()
    with pytest.raises(KeyError):
        registry.build("missing", root=tmp_path)


def test_build_uses_registered_builder(tmp_path: Path) -> None:
    registry = ExecutorRegistry()
    registry.register(ExecutorSpec(id="demo"), builder=lambda root, **kw: ("built", root))
    assert registry.build("demo", root=tmp_path) == ("built", tmp_path)


def test_build_without_builder_returns_none(tmp_path: Path) -> None:
    registry = ExecutorRegistry()
    registry.register(ExecutorSpec(id="demo"))
    assert registry.build("demo", root=tmp_path) is None


# ------------------------------------------------------------- default registry
def test_default_registry_declares_builtin_executors() -> None:
    ids = {spec.id for spec in default_registry().list()}
    assert {"none", "provider", "mcp", "test_stub", "patch"} <= ids


def test_builtin_capability_declarations_are_honest() -> None:
    registry = default_registry()
    none_spec = registry.get("none")
    assert none_spec is not None and none_spec.can_mutate is False
    assert none_spec.requires_network is False

    provider = registry.get("provider")
    assert provider is not None and provider.can_mutate is True
    assert provider.requires_network is True

    stub = registry.get("test_stub")
    assert stub is not None and stub.can_mutate is True
    assert stub.requires_network is False
    assert stub.can_run_commands is False

    patch = registry.get("patch")
    assert patch is not None and patch.can_mutate is True
    assert patch.can_run_commands is False
    assert patch.requires_network is False


def test_default_registry_is_a_cached_singleton() -> None:
    assert default_registry() is default_registry()


def test_default_registry_builds_test_stub_only_from_explicit_config(tmp_path: Path) -> None:
    # No config → no test_stub executor (never a production fallback).
    assert default_registry().build("test_stub", root=tmp_path) is None


def test_default_registry_builds_none_executor(tmp_path: Path) -> None:
    from opencontext_core.oc_flow.nodes import DeterministicNodeExecutor

    executor = default_registry().build("none", root=tmp_path)
    assert isinstance(executor, DeterministicNodeExecutor)


# ----------------------------------------------------------------- EXE-001 policy
def test_non_mutating_executor_cannot_mutate(tmp_path: Path) -> None:
    """EXE-001: the ``none`` executor (can_mutate=False) never mutates files."""
    from opencontext_core.oc_flow.runner import OCFlowRunner

    spec = default_registry().get("none")
    assert spec is not None and spec.can_mutate is False

    source = tmp_path / "calc.py"
    original = "def add(a, b):\n    return a - b\n"
    source.write_text(original, encoding="utf-8")

    executor = default_registry().build("none", root=tmp_path)
    result = OCFlowRunner(root=tmp_path, executor=executor).run("fix the bug in add")

    assert result.status == "needs_executor"
    assert source.read_text(encoding="utf-8") == original

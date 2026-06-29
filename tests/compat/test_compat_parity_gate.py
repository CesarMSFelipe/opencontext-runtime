"""Parity gate blocks a flag flip until parity is proven (SPEC CL-012)."""

from __future__ import annotations

import pytest

from opencontext_core.compat import (
    AdapterRegistry,
    LegacyProviderAdapter,
    LegacyWorkflowAdapter,
    ParityGateError,
    assert_parity,
    check_parity,
)


def test_check_parity_pass_and_fail() -> None:
    ok = check_parity("workflow_registry", "runtime.registry_enabled", [1, 2], [1, 2])
    assert ok.passed is True
    assert ok.mismatch is None

    bad = check_parity("workflow_registry", "runtime.registry_enabled", [1, 2], [9])
    assert bad.passed is False
    assert bad.mismatch is not None


def test_check_parity_custom_comparator() -> None:
    report = check_parity(
        "ctx",
        "runtime.context_engine_enabled",
        {"a": 1, "b": 2},
        {"b": 2, "a": 1},
        equals=lambda x, y: sorted(x.items()) == sorted(y.items()),
    )
    assert report.passed is True


def test_assert_parity_raises_only_on_failure() -> None:
    assert_parity(check_parity("s", "f", 1, 1))  # no raise
    with pytest.raises(ParityGateError):
        assert_parity(check_parity("s", "f", 1, 2))


def test_flip_rejected_until_parity_passes() -> None:
    reg = AdapterRegistry()
    reg.register(LegacyWorkflowAdapter())

    # Failing parity: flipping the flag to vNext is rejected (gate red).
    with pytest.raises(ParityGateError):
        reg.resolve("workflow_registry", flag_enabled=True, parity_passed=False)

    # Passing parity: the vNext route is selected.
    route = reg.resolve("workflow_registry", flag_enabled=True, parity_passed=True)
    assert route is not None


def test_flip_isolated_to_its_subsystem() -> None:
    reg = AdapterRegistry()
    reg.register(LegacyWorkflowAdapter())
    reg.register(LegacyProviderAdapter())

    # Flip only the workflow registry; the provider gateway stays legacy.
    workflow = reg.resolve("workflow_registry", flag_enabled=True, parity_passed=True)
    provider = reg.resolve("provider_gateway", flag_enabled=False)

    assert workflow == reg.get("workflow_registry").adapt
    assert provider == reg.get("provider_gateway").legacy

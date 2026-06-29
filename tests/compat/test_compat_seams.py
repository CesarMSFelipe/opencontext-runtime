"""The four named adapter seams advertise + defer correctly (SPEC CL-001..004)."""

from __future__ import annotations

import pytest

from opencontext_core.compat import (
    HarnessApiAdapter,
    LegacyAdapter,
    LegacyContextAdapter,
    LegacyProviderAdapter,
    LegacyWorkflowAdapter,
)

DEFERRED = [
    (LegacyWorkflowAdapter, "workflow_registry", "runtime.registry_enabled", "PR-003"),
    (LegacyProviderAdapter, "provider_gateway", "runtime.gateway_enabled", "PR-012"),
    (LegacyContextAdapter, "context_engine", "runtime.context_engine_enabled", "PR-010"),
]


def test_canonical_harness_seam_metadata() -> None:
    adapter = HarnessApiAdapter()
    assert adapter.subsystem == "runtime"
    assert adapter.flag == "runtime.session_wrapper"
    assert adapter.owning_pr == "PR-001"


@pytest.mark.parametrize("cls, subsystem, flag, pr", DEFERRED)
def test_deferred_seam_advertises_metadata(
    cls: type, subsystem: str, flag: str, pr: str
) -> None:
    adapter = cls()
    assert isinstance(adapter, LegacyAdapter)
    assert adapter.subsystem == subsystem
    assert adapter.flag == flag
    assert adapter.owning_pr == pr


@pytest.mark.parametrize("cls, subsystem, flag, pr", DEFERRED)
def test_deferred_seam_raises_naming_owning_pr(
    cls: type, subsystem: str, flag: str, pr: str
) -> None:
    adapter = cls()
    with pytest.raises(NotImplementedError) as adapt_exc:
        adapter.adapt()
    assert pr in str(adapt_exc.value)

    with pytest.raises(NotImplementedError) as legacy_exc:
        adapter.legacy()
    assert pr in str(legacy_exc.value)

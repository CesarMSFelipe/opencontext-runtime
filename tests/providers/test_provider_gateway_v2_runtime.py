"""PR-012 Phase 4.7 — the unified gateway works end-to-end behind the flag.

``runtime.gateway_enabled`` (default off) binds the unified ``ProviderGateway`` as
the runtime's gateway; a real generation flows through routing -> policy -> budget
-> dispatch and records a cost entry + events, without crashing. Air-gapped mode
still degrades to the local mock through the facade rather than reaching out.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from opencontext_core.config import default_config_data
from opencontext_core.models.llm import LLMRequest
from opencontext_core.providers.gateway import ProviderGateway
from opencontext_core.runtime import BudgetAwareLLMGateway, OpenContextRuntime


def _runtime(tmp: Path, *, gateway_enabled: bool, air_gapped: bool = False) -> OpenContextRuntime:
    data = default_config_data()
    data["runtime"]["gateway_enabled"] = gateway_enabled
    if air_gapped:
        data["security"]["mode"] = "air_gapped"
        data["security"]["external_providers_enabled"] = False
    cfg = tmp / "opencontext.yaml"
    cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
    return OpenContextRuntime(config_path=str(cfg), storage_path=tmp / ".storage")


def _req() -> LLMRequest:
    return LLMRequest(
        prompt="explain the runtime",
        provider="mock",
        model="mock-llm",
        max_output_tokens=128,
        metadata={"role": "generate"},
    )


def test_flag_off_uses_legacy_budget_gateway() -> None:
    tmp = Path(tempfile.mkdtemp())
    runtime = _runtime(tmp, gateway_enabled=False)
    assert isinstance(runtime.llm_gateway, BudgetAwareLLMGateway)


def test_flag_on_binds_unified_gateway_and_generates() -> None:
    tmp = Path(tempfile.mkdtemp())
    runtime = _runtime(tmp, gateway_enabled=True)
    assert isinstance(runtime.llm_gateway, ProviderGateway)

    resp = runtime.llm_gateway.generate(_req())
    assert resp.content  # a real (mock) answer, not a crash
    # The gateway recorded the call into the wired cost ledger and emitted events.
    assert len(runtime.cost_ledger.entries) == 1
    assert runtime.cost_ledger.entries[0].provider == "mock"
    assert runtime.provider_events.kinds()  # provider.* events were emitted


def test_flag_on_air_gapped_degrades_to_local_without_crashing() -> None:
    # The default config routes the 'mock' (local) provider, so air-gapped mode
    # stays fully local: the facade's policy filter allows the local route and the
    # call is served by the local mock gateway — never an external provider.
    tmp = Path(tempfile.mkdtemp())
    runtime = _runtime(tmp, gateway_enabled=True, air_gapped=True)
    assert isinstance(runtime.llm_gateway, ProviderGateway)
    resp = runtime.llm_gateway.generate(_req())
    assert resp.content  # local mock answer; no external provider reached
    assert resp.provider == "mock"

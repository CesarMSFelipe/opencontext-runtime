"""Host-model-via-MCP-sampling: prefer the host's selected model, no provider.

Verifies the gateway round-trip and that gateway resolution prefers a registered
host sampler over the mock default (the zero-config path), while air-gapped mode
forbids it. The global sampler registry is cleared after each test.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.llm.mock import MockLLMGateway
from opencontext_core.llm.sampling_gateway import (
    SamplingGateway,
    get_host_sampler,
    register_host_sampler,
)
from opencontext_core.models.llm import LLMRequest
from opencontext_core.runtime import OpenContextRuntime


@pytest.fixture
def host_sampler() -> Iterator[list[tuple[str, str, int, str | None]]]:
    """Register a recording host sampler and clear it afterward."""
    calls: list[tuple[str, str, int, str | None]] = []

    def _sampler(system: str, prompt: str, max_tokens: int, model: str | None = None) -> str:
        calls.append((system, prompt, max_tokens, model))
        return "HOST MODEL OUTPUT"

    register_host_sampler(_sampler)
    try:
        yield calls
    finally:
        register_host_sampler(None)


def test_registry_round_trip() -> None:
    assert get_host_sampler() is None
    register_host_sampler(lambda s, p, n, m: "x")
    try:
        assert get_host_sampler() is not None
    finally:
        register_host_sampler(None)
    assert get_host_sampler() is None


def test_sampling_gateway_calls_host_and_returns_content(host_sampler: list) -> None:
    gateway = SamplingGateway(get_host_sampler(), model="host-selected")
    resp = gateway.generate(
        LLMRequest(
            prompt="write a test",
            system_prompt="be terse",
            provider="host",
            model="m",
            max_output_tokens=256,
        )
    )
    assert resp.content == "HOST MODEL OUTPUT"
    assert resp.provider == "host"
    # sampler got the real args including the per-role model (forwarded as a hint)
    assert host_sampler == [("be terse", "write a test", 256, "m")]


def _mock_runtime(tmp: Path) -> OpenContextRuntime:
    data = default_config_data()  # provider defaults to mock
    (tmp / "opencontext.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    return OpenContextRuntime(
        config_path=str(tmp / "opencontext.yaml"), storage_path=tmp / ".storage"
    )


def test_runtime_prefers_host_sampler_over_mock(host_sampler: list) -> None:
    # Zero provider config (mock default), but a host sampler is present -> use it.
    runtime = _mock_runtime(Path(tempfile.mkdtemp()))
    # llm_gateway is wrapped (BudgetAware); resolve raw via the config path.
    gw = runtime._gateway_from_config()
    assert isinstance(gw, SamplingGateway)


def test_harness_resolves_host_executor_with_mock_config(host_sampler: list) -> None:
    # The executor must build (not scaffold) when the host model is available,
    # even though the config provider is mock.
    tmp = Path(tempfile.mkdtemp())
    _mock_runtime(tmp)  # writes opencontext.yaml (provider mock)
    runner = HarnessRunner(root=tmp)
    gateway, provider, _model = runner._resolve_gateway()
    assert isinstance(gateway, SamplingGateway)
    assert provider == "host"  # non-mock label -> build_phase_executor will build


def test_air_gapped_forbids_host_sampling(host_sampler: list) -> None:
    data = default_config_data()
    data["security"]["mode"] = "air_gapped"
    data["security"]["external_providers_enabled"] = False
    config = OpenContextConfig.model_validate(data)
    runtime = OpenContextRuntime.__new__(OpenContextRuntime)
    runtime.config = config
    # Even with a sampler registered, air-gapped must NOT delegate to the host —
    # it falls back to the local mock gateway, never SamplingGateway.
    gw = runtime._gateway_from_config()
    assert not isinstance(gw, SamplingGateway)
    assert isinstance(gw, MockLLMGateway)

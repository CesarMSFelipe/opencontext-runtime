"""Graceful provider failure for the productive OC Flow executor (PROD-001 / B3).

When the provider's fallback chain is exhausted at runtime the gateway raises a
``ProviderError``. ``ProviderBackedNodeExecutor.mutate`` MUST catch it, record a
redacted ``block_reason`` and return an empty edit set — so the failure flows
``node_mutate -> resolve_completion`` as a structured ``needs_provider`` status,
never a raw, unhandled Python traceback. An unparseable / schema-invalid edit set
stays ``blocked`` with the raw provider response redacted out of user-visible output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.errors import ProviderError
from opencontext_core.models.llm import LLMResponse
from opencontext_core.oc_flow.models import ContextEnvelope, Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    ProviderBackedNodeExecutor,
)
from opencontext_core.oc_flow.runner import OCFlowRunner


class _RaisingGateway:
    """Provider stub whose ``generate`` raises ``ProviderError`` (fallback exhausted).

    Honest stand-in for a runtime transport failure: it raises exactly what the real
    :class:`ProviderGateway` raises when its fallback chain is exhausted, so the
    executor's failure handling is exercised against the production error type.
    """

    def __init__(self, message: str) -> None:
        self._message = message
        self.calls: list[object] = []

    def generate(self, request: object) -> LLMResponse:  # pragma: no cover - raises
        self.calls.append(request)
        raise ProviderError(self._message)


class _StubGateway:
    """Deterministic provider stub returning a fixed response (no network)."""

    def __init__(self, content: str) -> None:
        self._content = content

    def generate(self, request: object) -> LLMResponse:
        return LLMResponse(
            content=self._content,
            provider="mock",
            model="stub",
            input_tokens=1,
            output_tokens=1,
        )


def _seed_buggy_calc(root: Path) -> None:
    (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")


def _contract_and_envelope() -> tuple[object, ContextEnvelope]:
    env = ContextEnvelope(task="Fix failing test")
    contract = DeterministicNodeExecutor().plan("Fix failing test", env)
    return contract, env


# ------------------------------------------------------- unit: mutate catches ProviderError
def test_mutate_catches_provider_error_returns_empty_and_blocks(tmp_path: Path) -> None:
    gateway = _RaisingGateway("provider_fallback_exhausted: connection reset")
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")
    contract, env = _contract_and_envelope()

    edits = executor.mutate(contract, env)  # type: ignore[arg-type]

    assert edits == []
    assert gateway.calls  # the gateway really was invoked
    assert executor.block_reason is not None
    assert executor.block_reason.startswith("provider_fallback_exhausted")
    # The provider is marked unavailable so the completion gate emits needs_provider.
    assert executor.provider_available is False


def test_mutate_block_reason_redacts_secrets_and_urls(tmp_path: Path) -> None:
    secret = "sk-ant-abcdefghijklmnopqrstuvwxyz0123456789"
    url = "https://api.example-provider.com/v1/messages"
    gateway = _RaisingGateway(f"provider_fallback_exhausted: 401 from {url} using key {secret}")
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")
    contract, env = _contract_and_envelope()

    executor.mutate(contract, env)  # type: ignore[arg-type]

    assert executor.block_reason is not None
    # No secret or endpoint leaks into the user-visible block_reason.
    assert secret not in executor.block_reason
    assert url not in executor.block_reason
    assert "REDACTED" in executor.block_reason


def test_mutate_provider_available_resets_between_calls(tmp_path: Path) -> None:
    # A failing call marks the executor unavailable; a subsequent valid call must
    # reset that state (no stale needs_provider carried across runs).
    raising = _RaisingGateway("provider_fallback_exhausted: boom")
    executor = ProviderBackedNodeExecutor(gateway=raising, root=tmp_path, provider="mock")
    contract, env = _contract_and_envelope()
    executor.mutate(contract, env)  # type: ignore[arg-type]
    assert executor.provider_available is False

    executor._gateway = _StubGateway(  # type: ignore[attr-defined]
        '[{"path":"calc.py","operation":"replace_range","start_line":2,"end_line":2,'
        '"content":"    return a + b","reason":"fix","requirement_refs":["c"]}]'
    )
    _seed_buggy_calc(tmp_path)
    edits = executor.mutate(contract, env)  # type: ignore[arg-type]
    assert edits  # a real edit was produced
    assert executor.provider_available is True
    assert executor.block_reason is None


# ------------------------------------------ integration: ProviderError -> needs_provider
def test_provider_error_run_yields_needs_provider_not_exception(tmp_path: Path) -> None:
    _seed_buggy_calc(tmp_path)
    gateway = _RaisingGateway("provider_fallback_exhausted: all providers timed out")
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")

    # No unhandled exception escapes the run; a structured status is returned instead.
    result = OCFlowRunner(root=tmp_path, executor=executor).run(
        "Fix failing test",
        lane=Lane.FAST,
    )

    assert result.status == "needs_provider"
    assert "provider_fallback_exhausted" in result.completion_reason
    # The bug was NOT mutated (no false completion).
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a - b\n"


def test_provider_error_run_reason_is_redacted(tmp_path: Path) -> None:
    _seed_buggy_calc(tmp_path)
    secret = "sk-abcdefghijklmnopqrstuvwxyz0123456789"
    gateway = _RaisingGateway(f"provider_fallback_exhausted: 403 key={secret}")
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")

    result = OCFlowRunner(root=tmp_path, executor=executor).run(
        "Fix failing test",
        lane=Lane.FAST,
    )

    assert result.status == "needs_provider"
    assert secret not in result.completion_reason


# ------------------------------------- invalid ApplyEdit stays blocked with redaction
def test_invalid_apply_edit_blocks_and_does_not_leak_raw_response(tmp_path: Path) -> None:
    _seed_buggy_calc(tmp_path)
    raw_response = "Sure! Here is the fix you asked for, no JSON though."
    gateway = _StubGateway(raw_response)
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")

    result = OCFlowRunner(root=tmp_path, executor=executor).run(
        "Fix failing test",
        lane=Lane.FAST,
    )

    assert result.status == "blocked"
    # The raw provider response is never surfaced in user-visible output.
    assert raw_response not in result.completion_reason
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a - b\n"


@pytest.mark.parametrize(
    "bad",
    [
        '[{"path":"calc.py","operation":"nuke_everything","wat":1}]',
        "not json at all",
    ],
)
def test_schema_invalid_edit_blocks_run(tmp_path: Path, bad: str) -> None:
    _seed_buggy_calc(tmp_path)
    gateway = _StubGateway(bad)
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")

    result = OCFlowRunner(root=tmp_path, executor=executor).run(
        "Fix failing test",
        lane=Lane.FAST,
    )

    assert result.status == "blocked"
    assert bad not in result.completion_reason
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a - b\n"

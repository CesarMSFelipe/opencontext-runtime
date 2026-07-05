"""REQ-pg-v2-003: FallbackReceipt on timeout + unsupported_capability."""

from __future__ import annotations

from opencontext_core.providers.v2.fallback import (
    FallbackChain,
    FallbackReason,
    FallbackReceipt,
)


def test_REQ_pg_v2_003_timeout() -> None:
    chain = FallbackChain(["mock-a", "mock-b"])
    receipt = chain.record_failure(
        provider_id="mock-a",
        reason=FallbackReason.timeout,
        error_message="deadline exceeded",
        attempted_at="2026-07-01T00:00:00Z",
    )
    assert isinstance(receipt, FallbackReceipt)
    assert receipt.provider_id == "mock-a"
    assert receipt.reason == FallbackReason.timeout
    assert "deadline" in receipt.error_message


def test_REQ_pg_v2_003_unsupported_capability() -> None:
    chain = FallbackChain([])
    receipt = chain.record_failure(
        provider_id="mock-text",
        reason=FallbackReason.unsupported_capability,
        error_message="vision not supported",
        attempted_at="2026-07-01T00:00:00Z",
    )
    assert receipt.reason == FallbackReason.unsupported_capability


def test_fallback_reasons_enum() -> None:
    assert {r.name for r in FallbackReason} >= {
        "timeout",
        "quota",
        "error",
        "unsupported_capability",
    }

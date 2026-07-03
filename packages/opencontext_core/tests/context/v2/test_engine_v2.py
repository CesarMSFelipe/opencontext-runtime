"""Tests for context.v2.engine — ContextEngine.build() returns 4-layer envelope + receipt."""

from __future__ import annotations

from opencontext_core.context.v2.engine import ContextEngine
from opencontext_core.context.v2.envelope import ContextEnvelope
from opencontext_core.context.v2.receipt import ContextReceipt


def _sample_items() -> list[dict]:
    return [
        {
            "id": "a",
            "content": "auth login flow",
            "recency": 0.9,
            "relevance": 0.9,
            "confidence": 0.8,
        },
        {
            "id": "b",
            "content": "weather forecast api",
            "recency": 0.3,
            "relevance": 0.1,
            "confidence": 0.4,
        },
        {
            "id": "c",
            "content": "auth token validation",
            "recency": 0.7,
            "relevance": 0.7,
            "confidence": 0.9,
        },
    ]


def test_returns_4_layers_and_receipt() -> None:
    engine = ContextEngine()
    out = engine.build(
        task="implement auth",
        items=_sample_items(),
        request_id="req-1",
        workflow="sdd",
        node="apply",
        budget=2000,
    )
    assert isinstance(out.envelope, ContextEnvelope)
    assert isinstance(out.receipt, ContextReceipt)
    assert out.envelope.task == "implement auth"
    assert out.receipt.task == "implement auth"
    assert out.receipt.request_id == "req-1"


def test_l4_sorted_by_usefulness() -> None:
    engine = ContextEngine()
    out = engine.build(
        task="auth",
        items=_sample_items(),
        request_id="req-2",
        workflow="sdd",
        node="apply",
        budget=2000,
    )
    # L4 usefulness = 0.5*rel + 0.3*fresh + 0.2*conf
    # a: 0.5*0.9 + 0.3*0.9 + 0.2*0.8 = 0.45 + 0.27 + 0.16 = 0.88
    # c: 0.5*0.7 + 0.3*0.7 + 0.2*0.9 = 0.35 + 0.21 + 0.18 = 0.74
    # b: 0.5*0.1 + 0.3*0.3 + 0.2*0.4 = 0.05 + 0.09 + 0.08 = 0.22
    ids = [item["id"] for item in out.envelope.items]
    assert ids.index("a") < ids.index("c") < ids.index("b")


def test_receipt_envelope_hash_matches() -> None:
    engine = ContextEngine()
    out = engine.build(
        task="auth",
        items=_sample_items(),
        request_id="req-3",
        workflow="sdd",
        node="apply",
        budget=2000,
    )
    # re-deriving the hash from the envelope should match receipt.envelope_hash
    import hashlib
    import json

    canonical = json.dumps(
        {
            "task": out.envelope.task,
            "items": out.envelope.items,
            "tokens_used": out.envelope.tokens_used,
            "budget": out.envelope.budget,
            "omissions": sorted(out.envelope.omissions),
        },
        sort_keys=True,
    ).encode("utf-8")
    expected = hashlib.sha256(canonical).hexdigest()
    assert out.receipt.envelope_hash == expected

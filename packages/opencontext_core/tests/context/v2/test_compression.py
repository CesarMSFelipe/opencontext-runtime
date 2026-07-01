"""Tests for context.v2.compression — token-budget compressor."""

from __future__ import annotations

from opencontext_core.context.v2.compression import ContextCompressor
from opencontext_core.context.v2.envelope import ContextEnvelope


def test_compress_drops_items_over_budget_and_marks_compressed() -> None:
    comp = ContextCompressor()
    env = ContextEnvelope(task="x", items=[
        {"id": "a", "content": "a" * 400},   # ~100 tokens
        {"id": "b", "content": "b" * 4000},  # ~1000 tokens
    ], budget=500)
    out = comp.compress(env, target_tokens=200)
    # only first item fits, second omitted
    assert [it["id"] for it in out.items] == ["a"]
    assert out.compressed is True
    assert any("b" in o for o in out.omissions)


def test_compress_uses_envelope_budget_when_target_unset() -> None:
    comp = ContextCompressor()
    env = ContextEnvelope(task="x", items=[
        {"id": "a", "content": "abc"},   # 0 tokens (3 // 4)
        {"id": "b", "content": "abcd" * 100},  # 100 tokens
    ], budget=10)
    out = comp.compress(env)
    assert out.tokens_used <= 10
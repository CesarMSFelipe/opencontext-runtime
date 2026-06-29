"""PR-010 SPEC-CTX-010-14: four typed retrieval receipts, out-of-band."""

from __future__ import annotations

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.context.engine import ContextEngine
from opencontext_core.context.receipt import (
    BudgetReceipt,
    CompressionReceipt,
    OmissionReceipt,
    QueryReceipt,
    RetrievalReceipts,
)
from opencontext_core.models.context import ContextItem, ContextPriority, RetrievalStrategy


def _engine() -> ContextEngine:
    cfg = OpenContextConfig.model_validate(default_config_data())
    comp = CompressionEngine(cfg.context.compression, semantic_protection=True)
    return ContextEngine(compression_engine=comp)


def _item(item_id: str, tokens: int = 30) -> ContextItem:
    return ContextItem(
        id=item_id,
        content=f"body {item_id} " * 3,
        source=f"{item_id}.py",
        source_type="file",
        priority=ContextPriority.P2,
        tokens=tokens,
        score=0.7,
    )


def test_all_four_receipts_are_emitted() -> None:
    res = _engine().build(
        "oc_flow", "gather_context", "add a method", candidates=[_item("a"), _item("b")]
    )
    receipts = res.receipts
    assert isinstance(receipts, RetrievalReceipts)
    assert isinstance(receipts.query, QueryReceipt)
    assert isinstance(receipts.budget, BudgetReceipt)
    assert isinstance(receipts.compression, CompressionReceipt)
    assert isinstance(receipts.omission, OmissionReceipt)


def test_query_receipt_records_strategy_and_sources() -> None:
    res = _engine().build("oc_flow", "gather_context", "task", candidates=[_item("a")])
    assert res.receipts.query.strategy is RetrievalStrategy.SYMBOL_FIRST
    assert "a.py" in res.receipts.query.sources
    assert res.receipts.query.candidate_count == 1


def test_receipts_are_out_of_band_not_in_prompt_body() -> None:
    res = _engine().build("oc_flow", "gather_context", "task", candidates=[_item("a")])
    # Receipts live on the result, never inside the envelope layers (the prompt body).
    serialized = str(res.envelope.model_dump())
    assert "QueryReceipt" not in serialized
    assert "BudgetReceipt" not in serialized
    assert "candidate_count" not in serialized
    assert not hasattr(res.envelope, "receipts")


def test_compression_receipt_savings_non_negative() -> None:
    res = _engine().build("oc_flow", "gather_context", "task", candidates=[_item("a", 30)])
    receipt = res.receipts.compression
    assert receipt.tokens_after <= receipt.tokens_before
    assert receipt.tokens_saved >= 0

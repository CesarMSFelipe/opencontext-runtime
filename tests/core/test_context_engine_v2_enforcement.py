"""PR-010 SPEC-CTX-010-11: budget validation of token_estimate at retrieval time."""

from __future__ import annotations

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.context.compression import CompressionEngine
from opencontext_core.context.engine import ContextEngine
from opencontext_core.models.context import ContextItem, ContextPriority


def _engine() -> ContextEngine:
    cfg = OpenContextConfig.model_validate(default_config_data())
    comp = CompressionEngine(cfg.context.compression, semantic_protection=True)
    return ContextEngine(compression_engine=comp)


def _item(item_id: str, tokens: int, score: float = 0.7) -> ContextItem:
    return ContextItem(
        id=item_id,
        content=f"content {item_id} " * 3,
        source=f"{item_id}.py",
        source_type="file",
        priority=ContextPriority.P2,
        tokens=tokens,
        score=score,
    )


def test_within_budget_envelope_reports_fit() -> None:
    res = _engine().build(
        "oc_flow", "gather_context", "small task", candidates=[_item("a", 20), _item("b", 20)]
    )
    assert res.receipts.budget.decision in {"fit", "compressed"}
    assert res.envelope.token_estimate <= res.receipts.budget.budget


def test_over_budget_envelope_triggers_gc_and_records_decision() -> None:
    # A large immutable contract (L2) plus discardable L1 working context pushes the
    # envelope over the small review budget; compression then GC must fire.
    res = _engine().build(
        "review",
        "review",
        "review the change",
        candidates=[_item("z", 10)],
        l2={"task": "x", "contract": "C " * 4000},
        l1_working={"obsolete_reasoning": "noise " * 4000, "diagnostics": "keep this"},
    )
    assert res.receipts.budget.decision in {"gc", "overflow"}
    # GC compacted L1: the obsolete reasoning was discarded and recorded as omission.
    assert "obsolete_reasoning" in res.discarded_l1_keys
    assert res.gc_output  # book attempt-summary emitted
    assert any(o.reason == "gc_discarded" for o in res.envelope.omissions)
    # The load-bearing diagnostics survived GC.
    assert res.envelope.l1.get("diagnostics") == "keep this"


def test_budget_receipt_carries_estimate_and_limit() -> None:
    res = _engine().build("oc_flow", "plan", "task", candidates=[_item("a", 30)])
    receipt = res.receipts.budget
    assert receipt.budget == 1000  # oc_flow/plan budget
    assert receipt.token_estimate == res.envelope.token_estimate

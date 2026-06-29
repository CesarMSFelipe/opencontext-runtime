"""Workflow what-if comparison + decision receipt, no reduction claim (SPEC-RI-011-09)."""

from __future__ import annotations

from opencontext_core.models.intelligence import WorkflowComparison
from opencontext_core.runtime_intelligence import events as ri_events
from opencontext_core.runtime_intelligence import telemetry_layout
from opencontext_core.runtime_intelligence.cost import CostEngine


def test_whatif_compares_sdd_and_oc_flow_and_stores_receipt(tmp_path) -> None:
    engine = CostEngine()
    comparison = engine.whatif("add a small helper function", root=tmp_path, emit=True)

    assert isinstance(comparison, WorkflowComparison)
    assert set(comparison.estimates) == {"oc-flow", "sdd"}
    assert comparison.chosen in {"oc-flow", "sdd"}
    assert comparison.advisory is True

    # A decision receipt was stored under the canonical layout.
    receipts = telemetry_layout.read_receipts(tmp_path)
    kinds = {r["kind"] for r in receipts}
    assert ri_events.RECEIPT_WORKFLOW_COMPARISON in kinds


def test_whatif_has_no_fabricated_reduction_field() -> None:
    engine = CostEngine()
    comparison = engine.whatif("refactor the module", emit=False)
    dumped = comparison.model_dump()
    for forbidden in ("reduction", "savings_pct", "cheaper_by", "percent_cheaper"):
        assert forbidden not in dumped


def test_whatif_high_risk_prefers_sdd() -> None:
    engine = CostEngine()
    comparison = engine.whatif(
        "fix a critical production security vulnerability", emit=False
    )
    assert comparison.chosen == "sdd"

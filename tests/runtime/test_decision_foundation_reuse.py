"""The decision layer reuses existing foundations, not parallel models (RB-010/011)."""

from __future__ import annotations

import opencontext_core.runtime.brain as brain_mod
import opencontext_core.runtime.decision_log as decision_log_mod
import opencontext_core.runtime.decisions as decisions_mod
from opencontext_core.agentic.receipt import AgenticReceipt
from opencontext_core.models.run_envelope import PolicyDecision


def test_brain_reuses_the_existing_agentic_receipt() -> None:
    assert brain_mod.AgenticReceipt is AgenticReceipt


def test_no_parallel_receipt_or_policy_model_is_defined() -> None:
    for module in (decisions_mod, decision_log_mod, brain_mod):
        assert not hasattr(module, "DecisionReceipt"), module.__name__
        # The decision modules must not redefine the receipt/policy schemas.
        receipt = getattr(module, "AgenticReceipt", None)
        assert receipt is None or receipt is AgenticReceipt
        policy = getattr(module, "PolicyDecision", None)
        assert policy is None or policy is PolicyDecision


def test_decision_log_entry_links_policy_via_reference_only() -> None:
    # The entry carries a policy_ref string, not an embedded PolicyDecision.
    fields = decision_log_mod.DecisionLogEntry.model_fields
    assert "policy_ref" in fields
    assert fields["policy_ref"].annotation == (str | None)

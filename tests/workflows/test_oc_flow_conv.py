"""OC Flow convergence tests (PR-007, FLOW-CONV §6):
lanes, Brain/auto/SDD-escalation, bounded diagnosis, surgical context, semantic
cache, decision receipts, profile-aware budgets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.oc_flow.budgets import (
    OC_FLOW_TOTAL_CEILING,
    lane_config,
)
from opencontext_core.oc_flow.models import ContextEnvelope, Lane, TaskContract
from opencontext_core.oc_flow.nodes import make_apply_edit
from opencontext_core.oc_flow.runner import (
    OCFlowRunner,
    select_workflow,
    should_escalate_to_sdd,
)
from opencontext_core.runtime.decisions import RuntimeDecision


# ---------------------------------------------------------------------- CONV.1 lanes
def test_careful_lane_raises_diagnosis_budget_and_strictness_over_fast() -> None:
    fast = lane_config(Lane.FAST)
    careful = lane_config(Lane.CAREFUL)
    assert careful.diagnosis_attempts > fast.diagnosis_attempts
    assert careful.context_depth > fast.context_depth
    # strictness ordering: advisory < warn < strict
    order = {"advisory": 0, "warn": 1, "strict": 2}
    assert order[careful.harness_strictness] > order[fast.harness_strictness]


def test_each_lane_maps_to_a_strategy() -> None:
    assert lane_config(Lane.FAST).strategy_id == "fast"
    assert lane_config(Lane.CHEAP).strategy_id == "cheap"
    assert lane_config(Lane.CAREFUL).strategy_id == "careful"


# ------------------------------------------------- CONV.2 auto selection + escalation
def test_auto_selects_oc_flow_for_localized_bugfix() -> None:
    assert select_workflow("Fix failing test") == "oc-flow"
    assert select_workflow("fix a lint error in one module") == "oc-flow"


def test_growing_scope_recommends_sdd() -> None:
    assert select_workflow("redesign the architecture of the auth subsystem") == "sdd"
    assert select_workflow("a schema migration across packages") == "sdd"


def test_contract_scope_growth_escalates_to_sdd() -> None:
    broad = TaskContract(
        scope="x",
        acceptance_criteria=["c"],
        verification_plan=["v"],
        changed_areas=[f"f{i}.py" for i in range(7)],
    )
    assert should_escalate_to_sdd(broad) is True
    narrow = TaskContract(
        scope="x",
        acceptance_criteria=["c"],
        verification_plan=["v"],
        changed_areas=["one.py"],
    )
    assert should_escalate_to_sdd(narrow) is False


def test_risk_flag_escalates_to_sdd() -> None:
    risky = TaskContract(
        scope="x",
        acceptance_criteria=["c"],
        verification_plan=["v"],
        changed_areas=["one.py"],
        risk_flags=["public_api"],
    )
    assert should_escalate_to_sdd(risky) is True


# ------------------------------------------------------------- CONV.2 advisory Brain
class _StubBrain:
    """A recommend-only Brain double (no side effects)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def recommend(
        self, *, run_id: str | None = None, runtime_context: dict[str, Any] | None = None
    ) -> RuntimeDecision | None:
        self.calls.append(dict(runtime_context or {}))
        return RuntimeDecision(
            kind="next_node",
            chosen=str((runtime_context or {}).get("proposed_node", "")),
            reason="advisory",
            confidence=0.5,
        )


def test_brain_is_advisory_only_graph_governs(tmp_path: Path) -> None:
    brain = _StubBrain()
    # Drive a real edit so this mutation task genuinely completes (a no-op mutation
    # would now honestly report needs_executor, not completed — B1/AVH-011); the
    # point of this test is that the Brain is advisory and the graph governs.
    edit = make_apply_edit(
        "fix.py", content="ok = 1\n", reason="fix", requirement_ref="task addressed"
    )
    result = OCFlowRunner(root=tmp_path, brain=brain).run(
        "Fix a null-pointer bug", lane=Lane.FAST, requested_edits=[edit]
    )
    # The Brain was consulted on transitions, and the graph still completed correctly.
    assert brain.calls
    assert result.status == "completed"
    # Decisions record the Brain recommendation but are governed by the state machine.
    govd = [d for d in result.decisions if d["governed_by"] == "state_machine"]
    assert govd


# -------------------------------------------------------- CONV.5 semantic cache reuse
def test_cache_hit_reused_and_recorded(tmp_path: Path) -> None:
    runner = OCFlowRunner(root=tmp_path, cache=object())
    # Seed the context so gather_context can reuse it from the (advisory) cache.
    runner.run("Fix failing test", lane=Lane.FAST)
    # Verify on the node directly that a pre-set envelope is reused (cache_hit recorded).
    from opencontext_core.oc_flow.nodes import (
        DeterministicNodeExecutor,
        OCFlowContext,
        node_gather_context,
    )

    artifacts = tmp_path / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    ctx = OCFlowContext(
        root=tmp_path,
        artifacts_dir=artifacts,
        task="t",
        lane=Lane.FAST,
        profile="balanced",
        executor=DeterministicNodeExecutor(),
        max_attempts=2,
        cache=object(),
        envelope=ContextEnvelope(task="t"),
    )
    result = node_gather_context(ctx)
    assert result.outputs["cache_hit"] is True
    assert ctx.cache_hits == 1
    assert result.llm_tokens == 0


# ------------------------------------------------------- CONV.6 decision receipts
def test_decision_receipt_persisted_per_transition(tmp_path: Path) -> None:
    # A real edit keeps the run on the happy path (a no-op mutation now routes through
    # escalation per the B1 inspection gate); this test asserts the per-transition
    # decision receipts on the verified-completion path.
    edit = make_apply_edit(
        "fix.py", content="ok = 1\n", reason="fix", requirement_ref="task addressed"
    )
    result = OCFlowRunner(root=tmp_path).run(
        "Fix a null-pointer bug", lane=Lane.FAST, requested_edits=[edit]
    )
    # One decision receipt per node transition on the happy path
    # (init->gather->plan->mutate->inspect->consolidation->completed = 6 transitions).
    assert len(result.decisions) == 6
    inspect_decision = next(
        d for d in result.decisions if d["kind"] == "next_node" and d["selected"] == "consolidation"
    )
    assert inspect_decision["rationale"]
    # The persisted decisions.json carries the same receipts.
    run_dir = result.artifacts_dir.parent.parent
    decisions_json = (run_dir / "decisions.json").read_text()
    assert "consolidation" in decisions_json


def test_surgical_context_uses_envelope_not_sdd_machinery(tmp_path: Path) -> None:
    # gather_context produces a typed ContextEnvelope (the PR-010 seam), recording
    # omissions — it does not build SDD's ContextPack.
    result = OCFlowRunner(root=tmp_path).run("Fix failing test", lane=Lane.FAST)
    import json

    envelope = json.loads((result.artifacts_dir / "context-envelope.json").read_text())
    assert envelope["schema_version"].startswith("opencontext.oc_flow.context_envelope")
    assert "omissions" in envelope


# ----------------------------------------------- CONV.7 profile-aware under ceiling
def test_balanced_profile_localized_bugfix_under_ceiling(tmp_path: Path) -> None:
    edit = make_apply_edit(
        "fix.py", content="ok = 1\n", reason="fix", requirement_ref="task addressed"
    )
    result = OCFlowRunner(root=tmp_path).run(
        "Fix a null-pointer bug", lane=Lane.FAST, profile="balanced", requested_edits=[edit]
    )
    assert result.status == "completed"
    assert result.total_tokens < OC_FLOW_TOTAL_CEILING

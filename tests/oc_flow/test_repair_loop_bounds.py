"""OC-REPAIR-BOUNDS — DOC2 §10.4 repair-loop limits.

The diagnosis/repair loop is bounded by its configured attempt ceiling and must
NOT run at all when the policy gate already blocked the run
(``forbidden_when: policy_blocked``), strict test-first evidence is absent
(``tdd_red_not_proven``), or no productive executor is available
(``missing_executor``). Each guard is pinned by invoking the loop under the
condition and asserting that no retry attempt is recorded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.oc_flow.budgets import resolve_max_attempts
from opencontext_core.oc_flow.models import (
    MAX_DIAGNOSIS_ATTEMPTS,
    InspectionReport,
    Lane,
    NodeOutcome,
)
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_diagnose,
    node_gather_context,
    node_plan,
)


def _looping_ctx(root: Path, max_attempts: int = 2, **overrides: Any) -> OCFlowContext:
    """A context primed for the diagnose loop (recoverable inspection failure)."""
    artifacts = root / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    ctx = OCFlowContext(
        root=root,
        artifacts_dir=artifacts,
        task="Fix failing test",
        lane=Lane.CAREFUL,
        profile="balanced",
        executor=DeterministicNodeExecutor(),
        max_attempts=max_attempts,
    )
    node_gather_context(ctx)
    node_plan(ctx)
    ctx.inspection = InspectionReport(
        outcome="failed_recoverable", failure_summary="assertion failed", llm_tokens=0
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def test_attempts_never_exceed_the_configured_ceiling(tmp_path: Path) -> None:
    """OC-REPAIR-BOUNDS — the loop never records more attempts than its configured
    ceiling, and the attempt resolver never exceeds MAX_DIAGNOSIS_ATTEMPTS."""
    ctx = _looping_ctx(tmp_path, max_attempts=2)
    outcomes = [node_diagnose(ctx).outcome for _ in range(5)]
    assert len(ctx.diagnosis_attempts) == 2, "attempts must stop at the configured ceiling"
    assert outcomes[2:] == [NodeOutcome.ATTEMPTS_EXHAUSTED] * 3
    for profile in ("balanced", "enterprise", "low-cost", "unknown-profile"):
        for lane in (None, Lane.FAST, Lane.CHEAP, Lane.CAREFUL):
            assert resolve_max_attempts(profile=profile, lane=lane) <= MAX_DIAGNOSIS_ATTEMPTS


def test_policy_blocked_run_never_enters_the_repair_loop(tmp_path: Path) -> None:
    """OC-REPAIR-BOUNDS — forbidden_when policy_blocked: once the policy gate
    blocked the run, invoking the loop records ZERO attempts and reports the
    POLICY_BLOCKED outcome."""
    ctx = _looping_ctx(tmp_path, policy_blocked=True)
    result = node_diagnose(ctx)
    assert result.outcome is NodeOutcome.POLICY_BLOCKED
    assert result.outputs.get("attempts") == 0
    assert result.outputs.get("forbidden") == "policy_blocked"
    assert ctx.diagnosis_attempts == [], "no retry attempt may be recorded"
    assert not (ctx.artifacts_dir / "diagnosis").exists()


def test_strict_red_not_proven_never_enters_the_repair_loop(tmp_path: Path) -> None:
    """OC-REPAIR-BOUNDS — forbidden_when tdd_red_not_proven: a strict mutation run
    without proven RED evidence (no red run, or an already-green red run) records
    ZERO diagnosis attempts."""
    for red_exit in (None, 0):
        ctx = _looping_ctx(
            tmp_path,
            mutation_required=True,
            tdd_mode="strict",
            tdd_red_exit_code=red_exit,
        )
        result = node_diagnose(ctx)
        assert result.outputs.get("forbidden") == "tdd_red_not_proven"
        assert result.outputs.get("attempts") == 0
        assert ctx.diagnosis_attempts == [], f"red_exit={red_exit}: no attempt may be recorded"


def test_missing_executor_never_enters_the_repair_loop(tmp_path: Path) -> None:
    """OC-REPAIR-BOUNDS — forbidden_when missing_executor: a mutation run that
    produced no edits and has no productive executor records ZERO attempts
    (retrying diagnosis can never yield an applicable fix)."""
    ctx = _looping_ctx(tmp_path, mutation_required=True)
    result = node_diagnose(ctx)
    assert result.outputs.get("forbidden") == "missing_executor"
    assert result.outputs.get("attempts") == 0
    assert ctx.diagnosis_attempts == [], "no retry attempt may be recorded"


def test_recoverable_failure_with_evidence_still_repairs(tmp_path: Path) -> None:
    """OC-REPAIR-BOUNDS — allowed_when verification_failed: a recoverable failure
    on a mutated run with strict RED proven still enters the loop (the guards
    must not over-fire and disable legitimate repair)."""
    ctx = _looping_ctx(
        tmp_path,
        mutation_required=True,
        tdd_mode="strict",
        tdd_red_exit_code=1,
        changed_files=["calc.py"],
    )
    result = node_diagnose(ctx)
    assert result.outcome is NodeOutcome.FIX_READY
    assert len(ctx.diagnosis_attempts) == 1

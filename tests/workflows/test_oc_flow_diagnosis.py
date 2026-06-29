"""OC Flow bounded-diagnosis tests (PR-007, FLOW-6)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.oc_flow.budgets import resolve_max_attempts
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_diagnose,
    node_gather_context,
    node_plan,
)


def test_max_attempts_balanced_is_two_enterprise_is_three() -> None:
    assert resolve_max_attempts(profile="balanced") == 2
    assert resolve_max_attempts(profile="enterprise") == 3
    assert resolve_max_attempts(profile="low-cost") == 1


def test_fast_lane_caps_attempts_careful_raises() -> None:
    assert resolve_max_attempts(profile="balanced", lane=Lane.FAST) == 1
    assert resolve_max_attempts(profile="balanced", lane=Lane.CAREFUL) == 3
    assert resolve_max_attempts(profile="balanced", lane=Lane.CHEAP) == 1


def _failed_ctx(root: Path, max_attempts: int) -> OCFlowContext:
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
    # Force a recoverable inspection failure to drive the loop.
    from opencontext_core.oc_flow.models import InspectionReport

    ctx.inspection = InspectionReport(
        outcome="failed_recoverable", failure_summary="assertion failed", llm_tokens=0
    )
    return ctx


def test_diagnosis_exhausts_after_budget_then_escalates(tmp_path: Path) -> None:
    ctx = _failed_ctx(tmp_path, max_attempts=2)
    r1 = node_diagnose(ctx)
    r2 = node_diagnose(ctx)
    r3 = node_diagnose(ctx)  # third request exceeds the budget of 2
    assert r1.outcome.value == "fix_ready"
    assert r2.outcome.value == "fix_ready"
    assert r3.outcome.value == "attempts_exhausted"
    assert len(ctx.diagnosis_attempts) == 2


def test_failed_strategy_is_never_retried(tmp_path: Path) -> None:
    ctx = _failed_ctx(tmp_path, max_attempts=3)
    node_diagnose(ctx)
    node_diagnose(ctx)
    strategies = [a.fix_strategy for a in ctx.diagnosis_attempts]
    assert strategies[0] != strategies[1]
    # The first strategy is recorded as ruled-out so it cannot be reselected.
    assert strategies[0] in ctx.failed_strategies


def test_attempt_artifacts_are_persisted(tmp_path: Path) -> None:
    ctx = _failed_ctx(tmp_path, max_attempts=2)
    node_diagnose(ctx)
    node_diagnose(ctx)
    diag_dir = ctx.artifacts_dir / "diagnosis"
    files = sorted(p.name for p in diag_dir.glob("attempt-*.json"))
    assert files == ["attempt-001.json", "attempt-002.json"]

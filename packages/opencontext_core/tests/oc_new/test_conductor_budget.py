"""Tests for G3 — ASK budget mode pauses flow (AC-G3-1, AC-G3-2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from opencontext_core.agentic.budget_controller import BudgetDecision
from opencontext_core.agentic.config import AgenticFlowConfig, BudgetMode
from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import ChangeIdentity, OcNewRunState, PhaseState


def _make_state(tmp_path: Path, config: AgenticFlowConfig | None = None) -> OcNewRunState:
    """Return a fresh run state with all phases pending."""
    identity = ChangeIdentity.from_task("budget-ask-test")
    phases = [PhaseState(name=p.name) for p in OC_NEW_FLOW]
    return OcNewRunState(identity=identity, task="budget-ask-test", phases=phases, config=config)


def test_ask_budget_mode_returns_request_approval(tmp_path: Path) -> None:
    """AC-G3-1: BudgetDecision(should_ask_user=True) → next_action.kind == 'request_approval'."""
    config = AgenticFlowConfig(budget_mode=BudgetMode.ASK)
    conductor = OcNewConductor(root=tmp_path)
    state = _make_state(tmp_path, config=config)

    # Mock _check_budget to return should_ask_user=True
    ask_decision = BudgetDecision(
        allowed=True,
        reason="ask mode: user confirmation requested",
        available_for_phase=8000,
        should_ask_user=True,
    )
    with patch.object(conductor, "_check_budget", return_value=ask_decision):
        result = conductor._advance(state)

    assert result.next_action is not None
    assert result.next_action.kind == "request_approval", (
        f"Expected 'request_approval', got {result.next_action.kind!r}"
    )


def test_non_ask_budget_continues_normally(tmp_path: Path) -> None:
    """AC-G3-2: BudgetDecision(should_ask_user=False) → flow does NOT return request_approval."""
    config = AgenticFlowConfig(budget_mode=BudgetMode.WARN)
    conductor = OcNewConductor(root=tmp_path)
    state = _make_state(tmp_path, config=config)

    warn_decision = BudgetDecision(
        allowed=True,
        reason="warn mode: 0 tokens used",
        available_for_phase=8000,
        should_ask_user=False,
    )
    with patch.object(conductor, "_check_budget", return_value=warn_decision):
        result = conductor._advance(state)

    # With no artifacts present, it should spawn the first phase (explore) as subagent,
    # not pause for budget approval.
    assert result.next_action is not None
    assert result.next_action.kind != "request_approval", (
        f"Expected flow to continue but got {result.next_action.kind!r}"
    )

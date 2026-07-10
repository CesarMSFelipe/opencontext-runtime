"""OC Flow's agent_execute handoff must direct option-based user decisions.

The ``agent_execute`` handoff is the agent-facing instruction surface OC Flow
returns when the host cannot sample and no provider is configured: the client
agent reads ``instructions`` and drives the edits itself. When that agent needs
a decision from the user (ambiguous scope, a design/tradeoff choice, an
approval gate) it must present SELECTABLE OPTIONS with a custom/'Other' escape
— host-aware: Claude Code's ``AskUserQuestion`` structured tool when present,
otherwise labelled options the user picks by letter/number. It must never force
one exact free-text string.

Both handoff builders (OC Flow run + non-OC-Flow SDD workflow) share the same
``_instructions`` playbook, so the directive is asserted on both surfaces.
"""

from __future__ import annotations

from opencontext_core.mcp.agent_handoff import _instructions


def _assert_option_question_directive(steps: list[str]) -> None:
    joined = "\n".join(steps)
    low = joined.lower()
    assert "AskUserQuestion" in joined, (
        "OC Flow handoff must name Claude Code's AskUserQuestion tool"
    )
    assert "option" in low, "OC Flow handoff must direct selectable options for decisions"
    assert "custom" in low and "other" in low, (
        "OC Flow handoff must always allow a custom/'Other' answer"
    )
    assert "letter" in low or "number" in low, (
        "OC Flow handoff fallback must let the user pick options by letter/number"
    )


def test_oc_flow_run_handoff_instructions_direct_option_questions() -> None:
    _assert_option_question_directive(_instructions(has_flow_run=True))


def test_sdd_workflow_handoff_instructions_direct_option_questions() -> None:
    _assert_option_question_directive(_instructions(has_flow_run=False))

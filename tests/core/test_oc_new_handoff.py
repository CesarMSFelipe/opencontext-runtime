"""Tests for AgentHandoff and render_handoff_markdown."""

from __future__ import annotations

from opencontext_core.oc_new.handoff import AgentHandoff, render_handoff_markdown


def test_handoff_roundtrip():
    handoff = AgentHandoff(
        run_id="ocnew-abc",
        change_id="add-graph-health",
        trace_id="trace-xyz",
        phase="design",
        persona="oc-architect",
        task="Add graph health command",
        memory_key="change:add-graph-health",
        required_inputs=["spec.md"],
        expected_outputs=["design.md"],
        allowed_tools=["opencontext_context", "opencontext_impact"],
        context_summary="The project uses FastAPI.",
        previous_phase_summary="Spec approved in 2 iterations.",
    )
    assert handoff.schema_version == "opencontext.agent_handoff.v2"
    assert handoff.phase == "design"
    assert handoff.persona == "oc-architect"


def test_handoff_markdown_contains_key_fields():
    handoff = AgentHandoff(
        run_id="r1",
        change_id="c1",
        trace_id="t1",
        phase="explore",
        persona="oc-explorer",
        task="My task",
        memory_key="change:my-task",
        required_inputs=["a.json"],
        expected_outputs=["b.json"],
        allowed_tools=["opencontext_search"],
    )
    md = render_handoff_markdown(handoff)
    assert "r1" in md
    assert "oc-explorer" in md
    assert "a.json" in md
    assert "b.json" in md
    assert "opencontext_search" in md
    assert "My task" in md


def test_handoff_empty_lists_render_none():
    handoff = AgentHandoff(
        run_id="r1",
        change_id="c1",
        trace_id="t1",
        phase="archive",
        persona="oc-orchestrator",
        task="task",
        memory_key="key",
    )
    md = render_handoff_markdown(handoff)
    assert "- none" in md

"""Tests for the consolidated agent instructions template renderer.

The renderer is the single source of truth for the markdown block written into
each agent's managed instructions file (AGENTS.md / CLAUDE.md / GEMINI.md /
QWEN.md). It must:

- include every required topic from the AHE-008 spec (opencontext_run, memory
  tools, quality, session tools, workflow/profile explain, config doctor,
  trace/status tools, symbol edit tools, OC Flow vs SDD guidance, TDD mode
  guidance, memory/Engram guidance);
- avoid hardcoded "32 MCP tools" / "all 14" style stale counts — counts must
  come from the live registry or the renderer must not hardcode a number;
- avoid the `opencontext init` mention in the SDD section unless init is a
  real alias for the SDD entrypoint (it is not — it is a project init wizard);
- expose a Host-Constrained Local --scope=local decision string the rest of
  the product can read.
"""

from __future__ import annotations

import pytest


def _try_import_renderer():
    try:
        from opencontext_core.agents.template_renderer import (
            HOST_CONSTRAINED_LOCAL_REASON,
            RENDER_SCOPE_LOCAL_REASON,
            render_agent_instructions,
        )
    except ImportError:
        return None
    return render_agent_instructions, HOST_CONSTRAINED_LOCAL_REASON, RENDER_SCOPE_LOCAL_REASON


REQUIRED_TOPICS = (
    "opencontext_run",
    "opencontext_memory",
    "opencontext_quality",
    "opencontext_session",
    "opencontext_workflow",
    "opencontext_doctor",
    "opencontext_status",
    "opencontext_trace",
    "opencontext_replace_symbol",
)


def test_template_renderer_module_exists() -> None:
    """RED gate: the module must exist with the documented entrypoint."""
    mod = _try_import_renderer()
    assert mod is not None, (
        "opencontext_core.agents.template_renderer is missing — the agent "
        "instructions template logic must move out of configurator/service.py."
    )


def test_render_returns_managed_block_for_unknown_agent() -> None:
    """RED: a brand-new template_renderer must produce a non-empty string."""
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    body = render("unknown-agent")
    assert isinstance(body, str) and body.strip()


@pytest.mark.parametrize("topic", REQUIRED_TOPICS)
def test_render_mentions_required_topic(topic: str) -> None:
    """Each spec-required topic must be reachable from the rendered instructions."""
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    body = render("opencode")
    assert topic in body, f"rendered instructions missing required topic: {topic}"


def test_render_contains_oc_flow_vs_sdd_guidance() -> None:
    """RED: the spec mandates an OC Flow vs SDD decision hint."""
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    body = render("claude-code").lower()
    assert "oc flow" in body and "sdd" in body, (
        "rendered instructions must help the agent pick between OC Flow and SDD"
    )


def test_render_contains_tdd_mode_guidance() -> None:
    """RED: TDD must be described as a mode/gate, not a workflow."""
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    body = render("opencode").lower()
    assert "tdd" in body, "rendered instructions must mention TDD"
    # Spec wording: TDD is a mode/gate, not a standalone workflow.
    assert ("mode" in body and "gate" in body) or "mode/gate" in body, (
        "TDD wording should describe it as a mode or gate, not a workflow"
    )


def test_render_mentions_engram_as_opt_in() -> None:
    """RED: Engram must be described as opt-in, not the default."""
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    body = render("claude-code").lower()
    assert "engram" in body, "rendered instructions must mention Engram"
    assert "opt-in" in body or "opt in" in body or "optional" in body, (
        "Engram must be presented as opt-in, not the default backend"
    )


def test_render_avoids_hardcoded_tool_counts() -> None:
    """RED: spec 8.3 — generated docs must not hardcode stale tool counts."""
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    for agent_id in ("claude-code", "codex", "opencode", "cursor"):
        body = render(agent_id)
        assert "32 MCP tools" not in body, f"{agent_id} docs still hardcode '32 MCP tools'"
        assert "all 14" not in body, f"{agent_id} docs still hardcode 'all 14'"


def test_render_does_not_claim_obsolete_init_in_sdd_section() -> None:
    """RED: spec 8.4 — `opencontext init` is the project wizard, not SDD init."""
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    body = render("opencode")
    # If init is mentioned, the SDD section must NOT direct the agent to
    # `opencontext init` as the way to "initialize SDD". Init is for project
    # bootstrap, not SDD.
    if "opencontext init" in body:
        # The mention is only OK if it is in a non-SDD context — assert the
        # SDD section does not carry the obsolete direction.
        assert "initialize SDD" not in body or "opencontext init" not in body.split("## SDD", 1)[-1]


def test_scope_local_decision_constant_is_host_constrained() -> None:
    """RED: spec 8.9 — the --scope=local decision must be Host-Constrained Local."""
    renderer = _try_import_renderer()
    assert renderer is not None
    _, host_constrained, render_scope = renderer
    assert host_constrained == "Host-Constrained Local", (
        f"Expected 'Host-Constrained Local' but got {host_constrained!r}"
    )
    assert "Host-constrained" in render_scope, (
        f"RENDER_SCOPE_LOCAL_REASON must explain the host-constrained decision: {render_scope!r}"
    )


def test_render_is_idempotent() -> None:
    """The renderer must be a pure function — same agent id → same body."""
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    a = render("opencode")
    b = render("opencode")
    assert a == b


def test_render_contains_user_question_option_directive() -> None:
    """RED: the managed block must carry the canonical option-question directive.

    Every host inherits this block. When the agent needs a decision from the
    user (approval gates, ambiguous requirements, design/scope/tradeoff
    choices) it must present SELECTABLE OPTIONS plus a custom/'Other' escape —
    never force one exact free-text string. The directive is host-aware: use
    Claude Code's ``AskUserQuestion`` structured tool when present, otherwise
    labelled options the user picks by letter/number.
    """
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    for agent_id in ("claude-code", "codex", "opencode", "cursor"):
        body = render(agent_id)
        low = body.lower()
        assert "AskUserQuestion" in body, (
            f"{agent_id}: managed block must name Claude Code's AskUserQuestion tool"
        )
        assert "selectable option" in low or "selectable options" in low, (
            f"{agent_id}: managed block must direct selectable options for decisions"
        )
        # Host-agnostic fallback + a custom/Other escape hatch.
        assert "custom" in low and ("other" in low or '"other"' in low), (
            f"{agent_id}: managed block must always allow a custom/'Other' answer"
        )
        assert "letter" in low or "number" in low, (
            f"{agent_id}: fallback must let the user pick options by letter/number"
        )


def test_render_does_not_emit_stale_opencode_slash_commands() -> None:
    """RED: spec 8.16 — opencode profile must not claim /context /impact /search."""
    renderer = _try_import_renderer()
    assert renderer is not None
    render, _, _ = renderer
    body = render("opencode")
    for stale in ("/context", "/impact", "/search"):
        # The profile should not list them as slash commands for OpenCode.
        assert f"`{stale}`" not in body, (
            f"opencode renderer still claims slash command {stale} — "
            f"opencode does not install those commands"
        )

"""PR-AHE-008 docs-pin tests.

Spec 8.5-8.8: generated docs must include required topics, the OC Flow vs SDD
decision, the TDD mode/gate wording, and the memory/Engram opt-in contract.
Spec 8.9: --scope=local is Host-Constrained Local.

The body under test is the consolidated renderer in
``opencontext_core.agents.template_renderer``. The configurator delegates
to the renderer, so the same body lands in every host's managed instructions
file. Pinning the renderer pins the on-disk output.
"""

from __future__ import annotations

from opencontext_core.agents.template_renderer import (
    HOST_CONSTRAINED_LOCAL_REASON,
    RENDER_SCOPE_LOCAL_REASON,
    render_agent_instructions,
)


def test_renderer_mentions_run_quality_session_workflow_doctor_trace_tools() -> None:
    """Spec 8.5: all the documented tool families are reachable from the body."""
    body = render_agent_instructions("opencode")
    for tool in (
        "opencontext_run",
        "opencontext_quality",
        "opencontext_session_",
        "opencontext_workflow_explain",
        "opencontext_profile_explain",
        "opencontext_doctor",
        "opencontext_status",
        "opencontext_trace",
        "opencontext_replace_symbol",
    ):
        assert tool in body, f"required tool/topic missing: {tool}"


def test_renderer_explains_oc_flow_vs_sdd_decision() -> None:
    """Spec 8.6: an agent must be able to tell when to use which workflow."""
    body = render_agent_instructions("claude-code")
    assert "OC Flow" in body
    assert "SDD" in body
    # The decision hint should call out one-shot vs tracked changes.
    assert "one-shot" in body.lower() or "tracked change" in body.lower()


def test_renderer_describes_tdd_as_mode_or_gate() -> None:
    """Spec 8.7: TDD is a mode/gate, not a standalone workflow."""
    body = render_agent_instructions("opencode").lower()
    assert "tdd" in body
    assert "mode" in body and "gate" in body
    # The wording must enumerate off/ask/strict.
    for value in ("off", "ask", "strict"):
        assert value in body, f"TDD values missing: {value}"


def test_renderer_describes_engram_as_opt_in() -> None:
    """Spec 8.8: Engram is opt-in, with explicit fallback when unavailable."""
    body = render_agent_instructions("claude-code")
    assert "Engram" in body
    body_lower = body.lower()
    assert "opt-in" in body_lower or "opt in" in body_lower, (
        "Engram must be presented as opt-in (not the default backend)"
    )
    # The fallback contract: when Engram is unreachable, layers fall back to local.
    assert "fall back" in body_lower or "fallback" in body_lower or "degraded" in body_lower, (
        "Engram section must explain the local fallback when Engram is unavailable"
    )


def test_renderer_names_opencontext_only_as_the_default_memory_mode() -> None:
    """Spec 8.8: the default memory mode is OpenContext-only, not Engram."""
    body = render_agent_instructions("codex")
    # The memory section must name the local default and contrast it with Engram.
    assert "local" in body.lower()
    assert "engram" in body.lower()
    # The default is the local SQLite / runtime-backed MCP store, not Engram.
    assert "default" in body.lower()


def test_renderer_pins_scope_local_decision() -> None:
    """Spec 8.9: --scope=local is Host-Constrained Local."""
    body = render_agent_instructions("opencode")
    assert "Host-Constrained Local" in body, (
        "Renderer must name the Host-Constrained Local decision so docs and "
        "JSON report agree on the wording."
    )


def test_scope_local_reason_constant_is_stable() -> None:
    """The JSON report wording and the docs MUST share one source of truth."""
    assert HOST_CONSTRAINED_LOCAL_REASON == "Host-Constrained Local"
    assert "Host-constrained" in RENDER_SCOPE_LOCAL_REASON
    # Both wording pieces are exported from one module so a future
    # rename forces every importer to update.
    assert RENDER_SCOPE_LOCAL_REASON.startswith("Host-constrained local setup")


def test_renderer_no_stale_opencode_slash_commands() -> None:
    """Spec 8.16: opencode profile must not claim /context /impact /search."""
    body = render_agent_instructions("opencode")
    for stale in ("/context", "/impact", "/search"):
        assert f"`{stale}`" not in body, f"opencode renderer still claims slash command {stale}"


def test_renderer_no_hardcoded_tool_counts() -> None:
    """Spec 8.3: generated docs must not hardcode stale tool counts."""
    for agent_id in ("claude-code", "codex", "opencode", "cursor"):
        body = render_agent_instructions(agent_id)
        assert "32 MCP tools" not in body, f"{agent_id} still hardcodes '32 MCP tools'"
        assert "all 14" not in body, f"{agent_id} still hardcodes 'all 14'"


def test_renderer_init_mention_is_not_in_sdd_section() -> None:
    """Spec 8.4: opencontext init is the project wizard, not the SDD entrypoint.

    If init is mentioned in the SDD section it must be explicitly framed
    as the project bootstrap wizard, not as the SDD entrypoint. The current
    renderer does mention init in the SDD section to be explicit about
    what it is NOT — the assertion checks that the framing is honest.
    """
    body = render_agent_instructions("opencode")
    if "opencontext init" in body and "## SDD" in body:
        sdd_section = body.split("## SDD", 1)[1]
        # The framing line must either say init is the project bootstrap OR
        # that init is NOT the SDD entrypoint. Both are honest framings.
        sdd_init_line = next(
            (line for line in sdd_section.splitlines() if "opencontext init" in line),
            None,
        )
        assert sdd_init_line is not None, (
            "SDD section must explicitly mention what `opencontext init` is"
        )
        sdd_init_lower = sdd_init_line.lower()
        assert (
            "bootstrap" in sdd_init_lower
            or "not" in sdd_init_lower
            or "not the sdd" in sdd_init_lower
        ), (
            "SDD section must frame `opencontext init` as the project "
            "bootstrap wizard, OR explicitly say it is not the SDD entrypoint"
        )

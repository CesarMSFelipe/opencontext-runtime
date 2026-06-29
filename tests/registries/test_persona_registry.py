"""PR-006 Persona Registry tests (AC-PA1..PA8 + REG-CONV CONV.1/CONV.2)."""

from __future__ import annotations

import pytest

from opencontext_core.actions.policy import ActionRequest, ActionType, evaluate_action
from opencontext_core.oc_new.models import AgentHandoff, ArtifactRef, render_handoff_markdown
from opencontext_core.personas import (
    PHASE_PERSONAS,
    Persona,
    PersonaDefinition,
    PersonaHandoff,
    PersonaNotFound,
    PersonaRegistry,
    PersonaResolver,
    get_persona,
    persona_for_phase,
)
from opencontext_core.workflow.phase_result import PhaseResultEnvelope

_CANONICAL = [
    "oc-orchestrator",
    "oc-explorer",
    "oc-architect",
    "oc-builder",
    "oc-reviewer",
    "oc-tester",
    "oc-context-engineer",
    "oc-requirements",
    "oc-planner",
    "oc-harness-verifier",
    "oc-archivist",
    "oc-evolution-steward",
]


# --- AC-PA1: PersonaDefinition full field set + legacy alias --------------------


def test_persona_definition_exposes_full_field_set() -> None:
    defn = PersonaRegistry.with_builtins().get("oc-builder")
    assert defn.responsibility
    assert "network" in defn.disallowed_tools
    assert "oc-apply-surgical" in defn.required_skills
    assert "ApplyEdit" in defn.output_contracts
    assert defn.token_budget >= 0
    assert isinstance(defn.escalation_rules, list)


def test_legacy_persona_still_resolves_unchanged() -> None:
    legacy = get_persona("oc-builder")
    assert legacy is not None
    assert "Edit" in legacy.tools  # tool surface unchanged
    assert legacy.system_prompt.startswith("You are the OC Builder")
    # round-trip: definition -> legacy preserves the load-bearing fields.
    back = PersonaRegistry.with_builtins().get("oc-builder").to_legacy()
    assert back.tools == legacy.tools
    assert back.system_prompt == legacy.system_prompt


# --- AC-PA2: PersonaRegistry ---------------------------------------------------


def test_registry_lists_all_builtins() -> None:
    reg = PersonaRegistry.with_builtins()
    assert len(reg.list()) == 15  # 12 canonical + professor + 2 new
    for pid in _CANONICAL:
        assert reg.has(pid)


def test_unknown_persona_raises_not_silent_none() -> None:
    with pytest.raises(PersonaNotFound):
        PersonaRegistry.with_builtins().get("oc-nonexistent")


# --- AC-PA3: twelve canonical personas + phase map -----------------------------


def test_each_canonical_persona_resolves_with_prompt_and_tools() -> None:
    reg = PersonaRegistry.with_builtins()
    for pid in _CANONICAL:
        defn = reg.get(pid)
        assert defn.system_prompt.strip()
        assert defn.default_tools


def test_phase_mapping_resolves_to_persona() -> None:
    assert persona_for_phase("apply").id == "oc-builder"
    assert PHASE_PERSONAS["apply"] == "oc-builder"
    resolver = PersonaResolver()
    assert resolver.resolve("apply").id == "oc-builder"


# --- AC-PA4: diagnostician + security-reviewer ---------------------------------


def test_diagnostician_registered_with_diagnosis_responsibility() -> None:
    defn = PersonaRegistry.with_builtins().get("oc-diagnostician")
    assert "three hypotheses" in defn.responsibility.lower()
    assert defn.strategy.diagnosis_policy == "three_hypotheses"
    assert defn.strategy.max_attempts == 3


def test_security_reviewer_is_read_only_security_persona() -> None:
    defn = PersonaRegistry.with_builtins().get("oc-security-reviewer")
    assert "security" in defn.responsibility.lower()
    # read-only: cannot edit/write (constraint-enforced).
    assert "Edit" in defn.disallowed_tools
    assert "Edit" not in defn.default_tools


# --- AC-PA5: PersonaResolver with overrides ------------------------------------


def test_role_resolves_to_default_persona() -> None:
    assert PersonaResolver().resolve_id("builder") == "oc-builder"


def test_profile_overrides_default_mapping() -> None:
    reg = PersonaRegistry.with_builtins()
    reg.register(PersonaDefinition(id="oc-custom-builder", name="Custom"))
    resolver = PersonaResolver(registry=reg, overrides={"team-x": {"builder": "oc-custom-builder"}})
    assert resolver.resolve_id("builder") == "oc-builder"
    assert resolver.resolve_id("builder", profile="team-x") == "oc-custom-builder"


# --- AC-PA6: PersonaHandoff explicit + serializable ----------------------------


def _handoff() -> AgentHandoff:
    return AgentHandoff(
        run_id="r",
        change_id="c",
        trace_id="t",
        phase="apply",
        persona="oc-builder",
        task="do thing",
        memory_key="change:c",
        required_inputs=["task_contract"],
        expected_outputs=["apply-manifest.json"],
        previous_phase_summary="design approved",
        artifact_refs=[ArtifactRef(key="design", path="design.md")],
        denied_tools=["network"],
    )


def test_handoff_carries_artifact_refs_not_raw_history() -> None:
    view = PersonaHandoff.from_agent_handoff(_handoff(), from_persona="oc-architect")
    assert view.from_persona == "oc-architect"
    assert view.to_persona == "oc-builder"
    assert view.artifact_refs == ["design.md"]
    assert view.next_expected_output == "apply-manifest.json"
    assert "deny:network" in view.constraints


def test_handoff_is_serializable() -> None:
    md = render_handoff_markdown(_handoff())
    assert "oc-builder" in md
    assert "apply-manifest.json" in md


# --- AC-PA7 / CONV.2: tool permissions enforced via policy ---------------------


def test_denied_tool_is_blocked_by_persona_policy() -> None:
    pol = PersonaRegistry.with_builtins().get("oc-builder").tool_policy()
    assert pol.allows("network") is False  # not in allowlist + in disallowed
    assert pol.allows("Edit") is True  # builder may edit


def test_read_only_persona_policy_blocks_writes() -> None:
    pol = PersonaRegistry.with_builtins().get("oc-explorer").tool_policy()
    assert pol.allows("Edit") is False
    assert pol.allows("Write") is False
    assert pol.allows("Read") is True


def test_allowlisted_tool_requires_approval_not_silent_allow() -> None:
    # AC-PA7 second scenario: an allowlisted runnable tool is 'ask', never an
    # unconditional allow (Policy Engine, PR-005).
    decision = evaluate_action(ActionRequest(action=ActionType.RUN_TEST))
    assert decision.decision == "ask"


# --- AC-PA8 / failure semantics ------------------------------------------------


def _envelope(status: str, **kw: object) -> PhaseResultEnvelope:
    base: dict[str, object] = {
        "run_id": "r",
        "change_id": "c",
        "phase": "apply",
        "status": status,
        "duration_s": 1.0,
    }
    base.update(kw)
    return PhaseResultEnvelope(**base)  # type: ignore[arg-type]


def test_needs_context_does_not_advance() -> None:
    assert _envelope("needs_context").can_advance() is False


def test_failed_contract_does_not_advance() -> None:
    assert _envelope("failed_contract").can_advance() is False


def test_done_advances() -> None:
    assert _envelope("done").can_advance() is True


def test_done_with_concerns_advances_when_no_missing_artifacts() -> None:
    assert _envelope("done_with_concerns").can_advance() is True


def test_done_with_concerns_blocked_by_missing_artifacts() -> None:
    env = _envelope("done_with_concerns", missing_artifacts=["spec.md"])
    assert env.can_advance() is False


# --- CONV.1: PersonaStrategy / Capabilities / Constraints ----------------------


def test_persona_is_responsibility_with_strategy_not_prompt_style() -> None:
    defn = PersonaRegistry.with_builtins().get("oc-builder")
    assert defn.strategy.enforce_output_contract is True
    assert "mutation" in defn.capabilities.required_harnesses
    assert "oc-apply-surgical" in defn.capabilities.required_skills
    assert defn.constraints.disallowed_tools  # constraints are typed, not prose


def test_from_legacy_preserves_prompt_and_tools() -> None:
    legacy = Persona(
        id="oc-x", name="X", description="d", system_prompt="P", tools=("Read", "Bash")
    )
    defn = legacy.to_definition(responsibility="r", required_skills=["oc-summary"])
    assert defn.system_prompt == "P"
    assert defn.default_tools == ["Read", "Bash"]
    assert defn.responsibility == "r"
    assert defn.capabilities.allowed_tools == ["Read", "Bash"]

"""OC Flow harness matrix / budgets / personas / skills tests
(PR-007, FLOW-9, FLOW-10, FLOW-11, FLOW-12)."""

from __future__ import annotations

from opencontext_core.harness.matrix import (
    OC_FLOW_HARNESS_MATRIX,
    SDD_HARNESS_MATRIX,
    oc_flow_posture_blocks,
    resolve_oc_flow_harness_mode,
)
from opencontext_core.oc_flow.budgets import (
    OC_FLOW_BUDGETS,
    OC_FLOW_TOTAL_CEILING,
    BudgetGuard,
)
from opencontext_core.oc_flow.personas import (
    OC_FLOW_NODE_PERSONAS,
    persona_for_oc_flow_node,
)
from opencontext_core.oc_flow.skills import (
    OC_FLOW_DEFAULT_BUNDLE,
    oc_flow_skill_registry,
    skills_for_node,
)


# --------------------------------------------------------------------- harness matrix
def test_mutation_harness_is_strict() -> None:
    assert OC_FLOW_HARNESS_MATRIX["mutation"] == "strict"
    assert resolve_oc_flow_harness_mode("mutation") == "strict"


def test_security_harness_is_conditional() -> None:
    assert OC_FLOW_HARNESS_MATRIX["security"] == "conditional"
    # conditional blocks only when the risk/capability condition is met.
    assert oc_flow_posture_blocks("conditional", condition_met=True) is True
    assert oc_flow_posture_blocks("conditional", condition_met=False) is False


def test_matrix_covers_book_postures() -> None:
    assert OC_FLOW_HARNESS_MATRIX["context"] == "strict"
    assert OC_FLOW_HARNESS_MATRIX["planning"] == "strict-lite"
    assert OC_FLOW_HARNESS_MATRIX["review"] == "optional"
    assert OC_FLOW_HARNESS_MATRIX["evaluation"] == "warn"


def test_sdd_matrix_untouched() -> None:
    # The OC Flow entry is additive — the SDD baseline is unchanged.
    assert SDD_HARNESS_MATRIX["protocol"] == "warn"
    assert SDD_HARNESS_MATRIX["mutation"] == "strict"


def test_profile_override_cannot_relax_strict() -> None:
    # low-cost relaxes inspection in SDD; OC Flow keeps inspection strict.
    assert resolve_oc_flow_harness_mode("inspection", profile="low-cost") == "strict"


# --------------------------------------------------------------------------- budgets
def test_local_inspection_budget_is_zero_llm() -> None:
    assert OC_FLOW_BUDGETS["local_inspection"] == (0, 0)


def test_total_guard_trips_over_ceiling() -> None:
    guard = BudgetGuard()
    guard.charge("gather_context", 4000)
    guard.charge("diagnose", 4000)
    assert guard.total_exceeds_ceiling() is False
    guard.charge("diagnose", 4000)  # cumulative now > 10k
    assert guard.total > OC_FLOW_TOTAL_CEILING
    assert guard.total_exceeds_ceiling() is True
    assert any(v.scope == "total" and v.severity == "fail" for v in guard.violations)


def test_per_node_hard_max_violation() -> None:
    guard = BudgetGuard()
    violations = guard.charge("plan", 5000)  # plan hard-max is 2000
    assert any(v.scope == "plan" and v.severity == "fail" for v in violations)


# -------------------------------------------------------------------------- personas
def test_oc_diagnostician_resolves() -> None:
    persona = persona_for_oc_flow_node("diagnose")
    assert persona is not None
    assert persona.id == "oc-diagnostician"
    assert persona.system_prompt
    assert persona.tools


def test_node_persona_map_matches_book() -> None:
    assert OC_FLOW_NODE_PERSONAS["init"] == "oc-orchestrator"
    assert OC_FLOW_NODE_PERSONAS["gather_context"] == "oc-context-engineer"
    assert OC_FLOW_NODE_PERSONAS["plan"] == "oc-architect"
    assert OC_FLOW_NODE_PERSONAS["mutate"] == "oc-builder"
    assert OC_FLOW_NODE_PERSONAS["local_inspection"] == "oc-harness-verifier"
    assert OC_FLOW_NODE_PERSONAS["diagnose"] == "oc-diagnostician"
    assert OC_FLOW_NODE_PERSONAS["escalation"] == "oc-orchestrator"
    assert OC_FLOW_NODE_PERSONAS["consolidation"] == "oc-archivist"


# ---------------------------------------------------------------------------- skills
def test_twelve_bundle_skills_resolve() -> None:
    registry = oc_flow_skill_registry()
    assert len(OC_FLOW_DEFAULT_BUNDLE) == 12
    for skill_id in OC_FLOW_DEFAULT_BUNDLE:
        assert registry.has(skill_id)
        assert registry.get(skill_id).id == skill_id


def test_diagnose_loads_diagnosis_skill_not_apply_skill() -> None:
    ids = {s.id for s in skills_for_node("diagnose")}
    assert "oc-diagnose-three-hypotheses" in ids
    assert "oc-apply-surgical" not in ids


def test_mutate_loads_apply_skill() -> None:
    ids = {s.id for s in skills_for_node("mutate")}
    assert "oc-apply-surgical" in ids
    assert "oc-diagnose-three-hypotheses" not in ids

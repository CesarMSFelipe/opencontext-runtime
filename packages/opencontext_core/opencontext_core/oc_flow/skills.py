"""The 12-skill ``oc_flow_default`` bundle (PR-007, FLOW-12, book doc 04 §16).

Each skill is a PR-006 :class:`SkillDefinition` (the contract-bearing model), so OC
Flow's bundle resolves through the same Skill registry surface as every other
workflow. ``workflow_nodes`` scopes a skill to the node(s) it serves; the node
loader (:func:`skills_for_node`) returns only the relevant subset, so ``diagnose``
loads the diagnosis skill and not the apply skill (book §16: "only relevant skills
should be loaded per node").

Layering (doc 58): L9 importing the L6 skills package downward.
"""

from __future__ import annotations

from opencontext_core.skills.definition import SkillDefinition
from opencontext_core.skills.registry import SkillRegistryV2

# The 12 default OC Flow skills (book §16), each scoped to its node(s).
_OC_FLOW_SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        id="oc-intent-clarify",
        name="Intent Clarify",
        tier="T0",
        category="Context",
        workflow_nodes=["init"],
        outputs=["clarified_intent"],
        token_budget=200,
    ),
    SkillDefinition(
        id="oc-context-discovery",
        name="Context Discovery",
        tier="T1",
        category="Context",
        workflow_nodes=["gather_context"],
        outputs=["context_envelope"],
        required_harnesses=["context", "kg"],
        token_budget=1200,
    ),
    SkillDefinition(
        id="oc-plan-discovery",
        name="Plan Discovery",
        tier="T1",
        category="Planning",
        workflow_nodes=["gather_context", "plan"],
        outputs=["plan_signals"],
        token_budget=600,
    ),
    SkillDefinition(
        id="oc-review-situation",
        name="Review Situation",
        tier="T1",
        category="Planning",
        workflow_nodes=["plan"],
        outputs=["situation_review"],
        token_budget=600,
    ),
    SkillDefinition(
        id="oc-strategy-compare",
        name="Strategy Compare",
        tier="T2",
        category="Planning",
        workflow_nodes=["plan"],
        outputs=["strategy_choice"],
        token_budget=600,
    ),
    SkillDefinition(
        id="oc-plan-lite",
        name="Plan Lite",
        tier="T1",
        category="Planning",
        workflow_nodes=["plan"],
        outputs=["task_contract"],
        required_harnesses=["planning", "protocol"],
        token_budget=800,
    ),
    SkillDefinition(
        id="oc-apply-surgical",
        name="Apply Surgical",
        tier="T1",
        category="Mutation",
        workflow_nodes=["mutate"],
        inputs=["task_contract", "focused_context"],
        outputs=["apply_edit", "receipt"],
        required_harnesses=["mutation", "inspection"],
        token_budget=1200,
    ),
    SkillDefinition(
        id="oc-inspect-local-first",
        name="Inspect Local First",
        tier="T1",
        category="Inspection",
        workflow_nodes=["local_inspection"],
        outputs=["inspection_report"],
        required_harnesses=["inspection"],
        token_budget=0,
    ),
    SkillDefinition(
        id="oc-diagnose-three-hypotheses",
        name="Diagnose Three Hypotheses",
        tier="T2",
        category="Diagnosis",
        workflow_nodes=["diagnose"],
        inputs=["failure"],
        outputs=["diagnosis_attempt"],
        required_harnesses=["diagnosis"],
        token_budget=1200,
    ),
    SkillDefinition(
        id="oc-semantic-gc",
        name="Semantic GC",
        tier="T2",
        category="Diagnosis",
        workflow_nodes=["diagnose", "consolidation"],
        inputs=["context_envelope"],
        outputs=["compressed_context"],
        token_budget=600,
    ),
    SkillDefinition(
        id="oc-escalate-owner",
        name="Escalate Owner",
        tier="T2",
        category="Consolidation",
        workflow_nodes=["escalation"],
        outputs=["handoff", "owner_candidates"],
        required_harnesses=["escalation"],
        token_budget=400,
    ),
    SkillDefinition(
        id="oc-archive-memory",
        name="Archive Memory",
        tier="T1",
        category="Consolidation",
        workflow_nodes=["consolidation"],
        outputs=["memory_delta", "graph_delta", "summary"],
        required_harnesses=["consolidation", "memory", "kg"],
        token_budget=600,
    ),
)

# The ordered bundle of skill ids (book §16 yaml: ``oc_flow_default``).
OC_FLOW_DEFAULT_BUNDLE: list[str] = [skill.id for skill in _OC_FLOW_SKILLS]


def oc_flow_skill_registry() -> SkillRegistryV2:
    """Return a registry holding the 12 ``oc_flow_default`` skills (FLOW-12)."""
    registry = SkillRegistryV2()
    for skill in _OC_FLOW_SKILLS:
        registry.register(skill)
    return registry


def skills_for_node(node: str, registry: SkillRegistryV2 | None = None) -> list[SkillDefinition]:
    """Return only the bundle skills scoped to ``node`` (node loader, FLOW-12).

    A skill belongs to a node when ``node`` is in its ``workflow_nodes``.
    """
    reg = registry or oc_flow_skill_registry()
    return [skill for skill in reg.list() if node in skill.workflow_nodes]

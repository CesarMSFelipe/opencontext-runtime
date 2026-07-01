"""Tests for skills.v2.bundle — SkillBundle Pydantic + SkillTier enum (CONV2)."""

from __future__ import annotations

from opencontext_core.skills.v2.bundle import SkillBundle, SkillTier


def test_skill_bundle_required_fields() -> None:
    """SkillBundle requires id/name/tier/profile/task/workflow_id/persona/gates/inputs/outputs."""
    b = SkillBundle(
        id="sdd",
        name="Spec-Driven Dev",
        tier=SkillTier.tier0,
        profile="balanced",
        task="implement auth",
        workflow_id="sdd",
        persona="senior-architect",
        gates=["check_ruff", "check_mypy"],
        inputs={"task": "x"},
        outputs=["decision"],
    )
    assert b.id == "sdd"
    assert b.tier is SkillTier.tier0


def test_skill_tier_enum_has_four_members() -> None:
    """SkillTier has exactly four members: tier0/tier1/tier2/tier3."""
    members = list(SkillTier)
    assert len(members) == 4
    names = {m.name for m in members}
    assert names == {"tier0", "tier1", "tier2", "tier3"}


def test_bundle_uses_session_first_runtime_api() -> None:
    """The skill bundle's workflow execution path goes through RuntimeApi.run(RunRequest)
    and dispatches per-node via WorkflowEngine.execute_node() — NOT through
    RuntimeApi.run_workflow() (which was deprecated by amendment A1).
    """
    import inspect

    from opencontext_core.skills.v2 import workflow

    src = inspect.getsource(workflow)
    # The function CALL must not appear (we tolerate the word in a docstring).
    assert ".run_workflow(" not in src, "skill workflow must NOT call run_workflow"
    assert "RuntimeApi" in src
    assert "execute_node" in src

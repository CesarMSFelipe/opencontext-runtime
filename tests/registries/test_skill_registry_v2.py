"""PR-006 Skill Registry v2 tests (AC-SK1..SK4 + REG-CONV CONV.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.skills.lifecycle import SkillInputError, run_skill
from opencontext_core.skills.registry import (
    SkillNotFound,
    SkillRegistryV2,
    build_registry,
    scan_skill_directory,
)

_CATEGORIES = {
    "Context",
    "Planning",
    "Mutation",
    "Inspection",
    "Diagnosis",
    "Review",
    "Consolidation",
}


# --- AC-SK1: SkillDefinition contract fields -----------------------------------


def test_skill_definition_exposes_contract_fields() -> None:
    s = SkillRegistryV2.with_builtins().get("oc-apply-surgical")
    assert s.inputs == ["task_contract", "focused_context"]
    assert s.outputs == ["apply_edit", "receipt"]
    assert "mutation" in s.required_harnesses
    assert s.required_capabilities == ["apply_edit"]
    assert s.token_budget == 1200
    assert s.tier == "T1"
    assert s.category == "Mutation"


# --- AC-SK2: scanner regression (coexists with v2) -----------------------------


def test_scanner_still_discovers_skill_md(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "py"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: py\ntrigger: python\n---\n- rule\n")
    entries = scan_skill_directory(tmp_path / "skills")
    assert len(entries) == 1
    assert entries[0].name == "py"


def test_project_overrides_user_by_name(tmp_path: Path) -> None:
    user = tmp_path / "user"
    proj = tmp_path / "proj"
    user.mkdir()
    proj.mkdir()
    (user / "SKILL.md").write_text("---\nname: x\n---\n- user rule\n")
    (proj / "SKILL.md").write_text("---\nname: x\n---\n- project rule\n")
    reg = build_registry(user_dirs=[str(user)], project_dirs=[str(proj)])
    assert len(reg) == 1
    assert reg[0].source == "project"


# --- AC-SK3: categorized skills, bundles, tiers --------------------------------


def test_every_category_has_at_least_one_skill() -> None:
    reg = SkillRegistryV2.with_builtins()
    present = reg.categories()
    for category in _CATEGORIES:
        assert reg.by_category(category), f"category {category} has no skill"
    assert _CATEGORIES <= present


def test_persona_bundle_resolves() -> None:
    bundle = {s.id for s in SkillRegistryV2.with_builtins().bundle("oc-builder")}
    assert "oc-apply-surgical" in bundle
    assert "oc-local-first-validation" in bundle


def test_every_skill_has_a_valid_tier() -> None:
    for s in SkillRegistryV2.with_builtins().list():
        assert s.tier in {"T0", "T1", "T2"}, f"{s.id} has bad tier {s.tier}"


def test_unknown_skill_raises() -> None:
    with pytest.raises(SkillNotFound):
        SkillRegistryV2.with_builtins().get("oc-nope")


# --- AC-SK4: lifecycle resolve->validate->execute->validate->receipt -----------


def test_missing_required_input_rejected_before_execution() -> None:
    executed = {"ran": False}

    def executor(defn, inputs):  # type: ignore[no-untyped-def]
        executed["ran"] = True
        return {"apply_edit": 1, "receipt": 1}

    with pytest.raises(SkillInputError):
        run_skill("oc-apply-surgical", {}, executor)
    assert executed["ran"] is False  # rejected pre-execution


def test_receipt_emitted_on_success_references_skill_and_outputs() -> None:
    sink: list[object] = []
    res = run_skill(
        "oc-apply-surgical",
        {"task_contract": 1, "focused_context": 2},
        lambda d, i: {"apply_edit": 1, "receipt": 1},
        receipt_sink=sink.append,
    )
    assert res.status == "done"
    assert res.receipt.skill_id == "oc-apply-surgical"
    assert set(res.receipt.outputs) == {"apply_edit", "receipt"}
    assert len(sink) == 1


def test_missing_output_yields_failed_contract() -> None:
    res = run_skill(
        "oc-apply-surgical",
        {"task_contract": 1, "focused_context": 2},
        lambda d, i: {"apply_edit": 1},  # 'receipt' missing
    )
    assert res.status == "failed_contract"
    assert res.missing_outputs == ["receipt"]


# --- CONV.3: skills are procedures with a tier + typed I/O ---------------------


def test_skills_are_procedures_not_prompt_snippets() -> None:
    for s in SkillRegistryV2.with_builtins().list():
        assert s.tier in {"T0", "T1", "T2"}
        assert s.inputs, f"{s.id} declares no typed inputs"
        assert s.outputs, f"{s.id} declares no typed outputs"

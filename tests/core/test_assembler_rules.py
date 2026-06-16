"""Tests for rules/persona injection into the assembled prompt ()."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.context.assembler import PromptAssembler
from opencontext_core.rules.loader import RulesConfig, RulesLoader


def test_resolved_rules_appear_in_assembled_prompt(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".opencontext" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "style.md").write_text("Prefer dataclasses over dicts\n", encoding="utf-8")

    loader = RulesLoader(RulesConfig())
    resolved = loader.resolve(project_root=tmp_path)

    prompt = PromptAssembler().assemble(
        "How should I model state?",
        [],
        rules=resolved,
    )

    # Rule text reaches the model.
    assert "Prefer dataclasses over dicts" in prompt.content
    # And it lives in a dedicated rules/persona section.
    rules_sections = [s for s in prompt.sections if s.name == "rules"]
    assert len(rules_sections) == 1
    assert "Prefer dataclasses over dicts" in rules_sections[0].content
    # High priority and trusted (at least as high as instructions / P1).
    assert int(rules_sections[0].priority) <= 1
    assert rules_sections[0].trusted is True


def test_empty_rule_set_yields_no_rules_section() -> None:
    # No rules argument -> backward compatible, no rules section, no crash.
    prompt = PromptAssembler().assemble("hello", [])
    assert all(s.name != "rules" for s in prompt.sections)


def test_secret_in_rule_is_redacted_in_assembled_prompt(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".opencontext" / "rules"
    rules_dir.mkdir(parents=True)
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    (rules_dir / "leak.md").write_text(f"Token is {secret}\n", encoding="utf-8")

    loader = RulesLoader(RulesConfig())
    resolved = loader.resolve(project_root=tmp_path)

    prompt = PromptAssembler().assemble("x", [], rules=resolved)
    # The raw secret must never appear in the assembled prompt.
    assert secret not in prompt.content
    rules_sections = [s for s in prompt.sections if s.name == "rules"]
    assert len(rules_sections) == 1
    assert rules_sections[0].redacted is True


def test_assembled_rules_section_records_provenance_source_ids(tmp_path: Path) -> None:
    rules_dir = tmp_path / ".opencontext" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "one.md").write_text("rule one\n", encoding="utf-8")
    (rules_dir / "two.md").write_text("rule two\n", encoding="utf-8")

    loader = RulesLoader(RulesConfig())
    resolved = loader.resolve(project_root=tmp_path)

    prompt = PromptAssembler().assemble("x", [], rules=resolved)
    rules_section = next(s for s in prompt.sections if s.name == "rules")
    # The applied rules' provenance flows into the section source ids so the
    # trace (prompt_sections) can enumerate exactly which rules were applied.
    assert rules_section.source_ids
    assert len(rules_section.source_ids) == len(resolved.applied)


def test_overridden_rules_not_in_applied_provenance(tmp_path: Path) -> None:
    global_root = tmp_path / "home"
    project_root = tmp_path / "proj"
    global_root.mkdir()
    project_root.mkdir()
    (global_root / ".opencontexthints").write_text(
        "project: G\n\n[conventions]\n- line_length=80\n", encoding="utf-8"
    )
    (project_root / ".opencontexthints").write_text(
        "project: P\n\n[conventions]\n- line_length=120\n", encoding="utf-8"
    )

    loader = RulesLoader(RulesConfig())
    resolved = loader.resolve(project_root=project_root, global_root=global_root)
    prompt = PromptAssembler().assemble("x", [], rules=resolved)

    rules_section = next(s for s in prompt.sections if s.name == "rules")
    # Only the winning rule appears; the overridden one does not.
    assert "line_length=120" in rules_section.content
    assert "line_length=80" not in rules_section.content

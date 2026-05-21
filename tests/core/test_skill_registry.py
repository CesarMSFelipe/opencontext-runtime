"""Tests for the skill registry scanner, compact rules, and resolver."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.skills.compact_rules import generate_compact_rules
from opencontext_core.skills.registry import (
    SkillEntry,
    _extract_compact_rules,
    _extract_triggers,
    _parse_frontmatter,
    build_registry,
    render_registry_markdown,
    scan_skill_directory,
)
from opencontext_core.skills.resolver import resolve_skills

SAMPLE_SKILL_MD = """\
---
name: "python-best-practices"
trigger: "python, typing, ruff"
---

# Python Best Practices

## Hard Rules
- Use strict typing, Python 3.12+
- Prefer Pydantic v2 models
- Use pytest, not unittest
- Use ruff for linting
- Never use bare except

## Patterns
- Use dataclasses for simple structs
- Use Protocol for duck typing
- Prefer Path over str for filesystem

## Examples
This is fluff that should not be included.
"""

SAMPLE_SKILL_2_MD = """\
---
name: "pytest-testing"
description: "Trigger: pytest testing patterns"
---

# Pytest Testing

## Hard Rules
- Use descriptive test names
- Use fixtures for setup
- Async tests use pytest.mark.asyncio
- Parametrize when possible

## Anti-patterns
- Never use time.sleep in tests
- Avoid global state in fixtures
"""


class TestFrontmatterParsing:
    def test_parse_simple_frontmatter(self) -> None:
        content = "---\nname: test\n---\nbody"
        result = _parse_frontmatter(content)
        assert result["name"] == "test"

    def test_parse_frontmatter_with_list(self) -> None:
        content = """---
keywords:
  - one
  - two
---
body
"""
        result = _parse_frontmatter(content)
        assert result["keywords"] == ["one", "two"]

    def test_no_frontmatter_returns_empty(self) -> None:
        result = _parse_frontmatter("No frontmatter here")
        assert result == {}


class TestTriggerExtraction:
    def test_extract_triggers_from_list(self) -> None:
        fm = {"trigger": ["python", "typing"]}
        triggers = _extract_triggers(fm)
        assert "python" in triggers
        assert "typing" in triggers

    def test_extract_triggers_from_description(self) -> None:
        fm = {"description": "Trigger: pytest testing patterns"}
        triggers = _extract_triggers(fm)
        assert "pytest testing patterns" in triggers


class TestCompactRulesExtraction:
    def test_extracts_actionable_lines(self) -> None:
        rules = _extract_compact_rules(SAMPLE_SKILL_MD, max_lines=10)
        assert "Use strict typing" in rules
        assert "Use pytest" in rules
        assert "This is fluff" not in rules  # examples filtered

    def test_skips_headers_and_empty_lines(self) -> None:
        rules = _extract_compact_rules(SAMPLE_SKILL_MD)
        assert "# Python" not in rules
        assert "## Hard Rules" not in rules


class TestScanSkillDirectory:
    def test_scans_single_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "skills" / "python"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(SAMPLE_SKILL_MD)

        entries = scan_skill_directory(tmp_path / "skills")

        assert len(entries) == 1
        assert entries[0].name == "python-best-practices"
        assert "user" in entries[0].source
        assert "python" in entries[0].triggers

    def test_returns_empty_for_missing_dir(self) -> None:
        entries = scan_skill_directory("/nonexistent/path")
        assert entries == []

    def test_scans_nested_directories(self, tmp_path: Path) -> None:
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "SKILL.md").write_text(SAMPLE_SKILL_MD)
        (tmp_path / "a" / "b" / "SKILL.md").write_text(SAMPLE_SKILL_2_MD)

        entries = scan_skill_directory(tmp_path)

        assert len(entries) == 2
        names = {e.name for e in entries}
        assert "python-best-practices" in names
        assert "pytest-testing" in names


class TestBuildRegistry:
    def test_deduplicates_by_name_project_wins(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user"
        proj_dir = tmp_path / "project"
        user_dir.mkdir()
        proj_dir.mkdir()

        (user_dir / "SKILL.md").write_text("---\nname: python\n---\n- User rule\n")
        (proj_dir / "SKILL.md").write_text("---\nname: python\n---\n- Project rule\n")

        registry = build_registry(
            user_dirs=[str(user_dir)],
            project_dirs=[str(proj_dir)],
        )

        assert len(registry) == 1
        assert registry[0].source == "project"
        assert "Project rule" in registry[0].compact_rules

    def test_merges_unique_skills(self, tmp_path: Path) -> None:
        user_dir = tmp_path / "user"
        proj_dir = tmp_path / "project"
        user_dir.mkdir()
        proj_dir.mkdir()

        (user_dir / "SKILL.md").write_text("---\nname: user-skill\n---\n- Rule A\n")
        (proj_dir / "SKILL.md").write_text("---\nname: project-skill\n---\n- Rule B\n")

        registry = build_registry(
            user_dirs=[str(user_dir)],
            project_dirs=[str(proj_dir)],
        )

        assert len(registry) == 2
        names = {e.name for e in registry}
        assert "user-skill" in names
        assert "project-skill" in names


class TestCompactRulesGeneration:
    def test_generates_markdown_block(self) -> None:
        skills = [
            SkillEntry(
                name="python",
                path=Path("/skills/python/SKILL.md"),
                triggers=["python"],
                compact_rules="- Use strict typing\n- Prefer Pydantic",
                source="user",
            )
        ]

        block = generate_compact_rules(skills)
        assert "### python" in block
        assert "Use strict typing" in block

    def test_skips_empty_rules(self) -> None:
        skills = [
            SkillEntry(
                name="empty",
                path=Path("/skills/empty/SKILL.md"),
                triggers=[],
                compact_rules="   ",
                source="user",
            )
        ]

        block = generate_compact_rules(skills)
        assert "### empty" not in block


class TestResolver:
    def test_matches_by_task_context(self) -> None:
        skills = [
            SkillEntry(
                name="pytest",
                path=Path("/skills/pytest/SKILL.md"),
                triggers=["pytest", "testing"],
                compact_rules="- Use fixtures",
                source="user",
            ),
            SkillEntry(
                name="go",
                path=Path("/skills/go/SKILL.md"),
                triggers=["go", "golang"],
                compact_rules="- Use interfaces",
                source="user",
            ),
        ]

        matched = resolve_skills(skills, file_patterns=[], task_type="write pytest tests")

        assert len(matched) == 1
        assert matched[0].name == "pytest"

    def test_matches_by_file_pattern(self) -> None:
        skills = [
            SkillEntry(
                name="python",
                path=Path("/skills/python/SKILL.md"),
                triggers=["python"],
                compact_rules="- Use typing",
                source="user",
            ),
            SkillEntry(
                name="typescript",
                path=Path("/skills/ts/SKILL.md"),
                triggers=["typescript"],
                compact_rules="- Use strict",
                source="user",
            ),
        ]

        matched = resolve_skills(skills, file_patterns=["*/python/*"], task_type="review")

        assert len(matched) == 1
        assert matched[0].name == "python"

    def test_caps_at_max_matches(self) -> None:
        skills = [
            SkillEntry(
                name=f"skill{i}",
                path=Path(f"/skills/skill{i}/SKILL.md"),
                triggers=["test"],
                compact_rules=f"- Rule {i}",
                source="user",
            )
            for i in range(10)
        ]

        matched = resolve_skills(skills, file_patterns=[], task_type="test", max_matches=3)

        assert len(matched) == 3


class TestRenderRegistryMarkdown:
    def test_renders_entries(self, tmp_path: Path) -> None:
        (tmp_path / "SKILL.md").write_text(SAMPLE_SKILL_MD)
        entries = scan_skill_directory(tmp_path)

        markdown = render_registry_markdown(entries)

        assert "# Skill Registry" in markdown
        assert "python-best-practices" in markdown
        assert "user" in markdown

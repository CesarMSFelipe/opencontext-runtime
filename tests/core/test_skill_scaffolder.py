"""Tests for skill scaffolder."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.skills.scaffolder import scaffold_skill


class TestScaffoldSkill:
    """Test scaffold_skill function."""

    def test_creates_directory_and_files(self, tmp_path: Path) -> None:
        result = scaffold_skill(
            name="test-skill",
            output_dir=str(tmp_path),
            description="A test skill",
            triggers="test, example",
            author="Tester",
        )
        skill_dir = Path(result)
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "README.md").exists()

    def test_skil_md_has_frontmatter(self, tmp_path: Path) -> None:
        scaffold_skill(
            name="my-skill",
            output_dir=str(tmp_path),
            description="My desc",
            triggers="trigger1",
            author="Me",
        )
        content = (tmp_path / "my-skill" / "SKILL.md").read_text(encoding="utf-8")
        assert "name: my-skill" in content
        assert "description: My desc" in content
        assert "triggers: trigger1" in content
        assert "author: Me" in content
        assert "version: 0.1.0" in content

    def test_force_guard_raises_on_existing(self, tmp_path: Path) -> None:
        scaffold_skill(name="existing", output_dir=str(tmp_path))
        import pytest
        with pytest.raises(FileExistsError):
            scaffold_skill(name="existing", output_dir=str(tmp_path), force=False)

    def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        scaffold_skill(name="skill1", output_dir=str(tmp_path), description="old")
        scaffold_skill(
            name="skill1",
            output_dir=str(tmp_path),
            description="new",
            force=True,
        )
        content = (tmp_path / "skill1" / "SKILL.md").read_text(encoding="utf-8")
        assert "description: new" in content

    def test_defaults_for_missing_fields(self, tmp_path: Path) -> None:
        scaffold_skill(name="minimal", output_dir=str(tmp_path))
        content = (tmp_path / "minimal" / "SKILL.md").read_text(encoding="utf-8")
        assert "description: No description provided." in content
        assert "triggers: Not specified" in content
        assert "author: Unknown" in content

    def test_skil_md_has_required_sections(self, tmp_path: Path) -> None:
        scaffold_skill(name="sections-test", output_dir=str(tmp_path))
        content = (tmp_path / "sections-test" / "SKILL.md").read_text(encoding="utf-8")
        assert "## Overview" in content
        assert "## Implementation" in content
        assert "## Common Mistakes" in content

    def test_readme_created(self, tmp_path: Path) -> None:
        scaffold_skill(name="readme-test", output_dir=str(tmp_path), description="RDESC")
        content = (tmp_path / "readme-test" / "README.md").read_text(encoding="utf-8")
        assert "RDESC" in content
        assert "# readme-test Skill" in content

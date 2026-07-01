"""SDD skills directory tests: SKILL.md files with valid frontmatter.

Per openspec/changes/agentic-parity-engram-gentle/tasks.md §PR4.b — T4.13.
"""

from __future__ import annotations

from pathlib import Path

import yaml

SDD_SKILLS = (
    Path(__file__).parents[2] / "packages" / "opencontext_sdd" / "opencontext_sdd" / "skills"
)

EXPECTED_SKILLS: set[str] = {
    "branch-pr",
    "chained-pr",
    "work-unit-commits",
    # PR4.c adds: cognitive-doc-design, comment-writer
}


class TestSkillsDirectory:
    def test_skills_directory_exists(self) -> None:
        assert SDD_SKILLS.is_dir(), f"Skills directory not found at {SDD_SKILLS}"

    def test_expected_skill_dirs_exist(self) -> None:
        found = {d.name for d in SDD_SKILLS.iterdir() if d.is_dir()}
        missing = EXPECTED_SKILLS - found
        assert not missing, f"Missing skill directories: {missing}"

    def test_each_skill_has_skill_md(self) -> None:
        for skill in EXPECTED_SKILLS:
            skill_md = SDD_SKILLS / skill / "SKILL.md"
            assert skill_md.is_file(), f"Missing {skill_md}"

    def test_skill_md_has_valid_frontmatter(self) -> None:
        for skill in EXPECTED_SKILLS:
            skill_md = SDD_SKILLS / skill / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{skill}: missing frontmatter delimiter"
            parts = content.split("---", 2)
            assert len(parts) >= 3, f"{skill}: frontmatter not closed"
            frontmatter = yaml.safe_load(parts[1])
            assert frontmatter is not None, f"{skill}: empty frontmatter"
            assert "name" in frontmatter, f"{skill}: missing 'name' in frontmatter"
            assert "description" in frontmatter, f"{skill}: missing 'description'"
            assert "license" in frontmatter, f"{skill}: missing 'license'"

    def test_chained_pr_has_references(self) -> None:
        ref = SDD_SKILLS / "chained-pr" / "references" / "chaining-details.md"
        assert ref.is_file(), f"Missing chained-pr reference file {ref}"

    def test_skill_count_at_least_3(self) -> None:
        skill_dirs = [d for d in SDD_SKILLS.iterdir() if d.is_dir()]
        assert len(skill_dirs) >= 3, f"Expected at least 3 skills, found {len(skill_dirs)}"

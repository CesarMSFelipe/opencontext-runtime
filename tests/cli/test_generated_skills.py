"""Tests for generated per-phase SDD skill stubs (CAP6 — opt-in, project ns).

Skill stubs MUST land under ``.opencontext/skills/oc-sdd-{phase}-{change}.md``
and MUST NEVER touch ``~/.claude/skills/``. Generation MUST be opt-in:
the default returns ``None`` and writes nothing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from opencontext_core.sdd.generated_skills import write_skill_stub


def test_default_is_disabled_returns_none(tmp_path: Path) -> None:
    result = write_skill_stub(
        project_root=tmp_path,
        change_id="my-change",
        phase="design",
        body="# design skill\n",
    )
    assert result is None
    assert not (tmp_path / ".opencontext" / "skills").exists()


def test_opt_in_writes_project_namespace_skill(tmp_path: Path) -> None:
    path = write_skill_stub(
        project_root=tmp_path,
        change_id="my-change",
        phase="design",
        body="# design skill stub\nUse when authoring design.md\n",
        enabled=True,
    )

    assert path is not None
    assert path == tmp_path / ".opencontext" / "skills" / "oc-sdd-design-my-change.md"
    assert path.exists()
    body = path.read_text()
    assert "design skill stub" in body
    assert "Use when authoring design.md" in body


def test_never_writes_under_claude_skills(tmp_path: Path) -> None:
    """Defence-in-depth: scan whole fake home for any leak."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with patch.object(Path, "home", lambda: fake_home):
        path = write_skill_stub(
            project_root=tmp_path,
            change_id="safe-change",
            phase="apply",
            body="# apply skill\n",
            enabled=True,
        )
        assert path is not None
        # Walk the entire fake home; no .claude/skills leak may exist.
        for f in fake_home.rglob("*"):
            assert ".claude" not in f.parts, f"unexpected leak: {f}"


def test_opt_in_does_not_overwrite_existing_skill(tmp_path: Path) -> None:
    """Generated skills are stub-only; if a stub already exists, return the existing path."""
    skills_dir = tmp_path / ".opencontext" / "skills"
    skills_dir.mkdir(parents=True)
    existing = skills_dir / "oc-sdd-design-my-change.md"
    existing.write_text("# user-maintained content\n")

    path = write_skill_stub(
        project_root=tmp_path,
        change_id="my-change",
        phase="design",
        body="# new content\n",
        enabled=True,
    )

    assert path == existing
    assert existing.read_text() == "# user-maintained content\n"


def test_phase_and_change_id_are_sanitised_in_filename(tmp_path: Path) -> None:
    path = write_skill_stub(
        project_root=tmp_path,
        change_id="feature_X",
        phase="spec",
        body="x",
        enabled=True,
    )
    assert path is not None
    assert path.name == "oc-sdd-spec-feature_X.md"
    # ponytail: assert NOT pointing at home claude skills.
    assert ".claude" not in path.parts

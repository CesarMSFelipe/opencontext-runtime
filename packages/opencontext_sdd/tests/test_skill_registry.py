"""Tests for the native skill-registry producer (REQ-OSR-001..005).

Per strict-TDD: this file is the source of truth for the skill-registry
contract. The module in ``opencontext_sdd.skill_registry`` is written
to satisfy these tests.

T1.16 — ``test_REQ_OSR_001_fingerprint_unchanged_skips_write`` written first.
T1.18 — Remaining REQ-OSR-* scenarios added RED-first.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from opencontext_sdd.skill_registry import (
    SkillEntry,
    SkillNotFound,
    get_skill_paths,
    match_skills,
    refresh,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(parent: Path, name: str, description: str) -> Path:
    """Create ``<parent>/<name>/SKILL.md`` with frontmatter."""
    d = parent / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# Body\n",
        encoding="utf-8",
    )
    return d / "SKILL.md"


# ---------------------------------------------------------------------------
# REQ-OSR-001 — Refresh skips when fingerprint unchanged (T1.16)
# ---------------------------------------------------------------------------


def test_REQ_OSR_001_fingerprint_unchanged_skips_write(tmp_path: Path) -> None:
    """First refresh writes registry+cache; second refresh with unchanged
    skills is a no-op (registry mtime is NOT touched, no cache rewrite)."""
    skills = tmp_path / "skills"
    (skills / "chained-pr").mkdir(parents=True)
    skill_path = skills / "chained-pr" / "SKILL.md"
    skill_path.write_text(
        "---\nname: chained-pr\ndescription: Plan a stacked PR sequence.\n---\n\n# Skill\n",
        encoding="utf-8",
    )

    # First refresh — files written
    first = refresh(tmp_path, source_dirs=[skills])
    assert first.changed is True
    assert (tmp_path / ".atl" / "skill-registry.md").exists()
    assert (tmp_path / ".atl" / ".skill-registry.cache.json").exists()
    registry_mtime = (tmp_path / ".atl" / "skill-registry.md").stat().st_mtime_ns

    # Second refresh — fingerprint unchanged, no write
    second = refresh(tmp_path, source_dirs=[skills])
    assert second.changed is False
    assert (tmp_path / ".atl" / "skill-registry.md").stat().st_mtime_ns == registry_mtime

    # Third refresh with force=True — always rewrites
    third = refresh(tmp_path, source_dirs=[skills], force=True)
    assert third.changed is True


# ---------------------------------------------------------------------------
# REQ-OSR-002 — Exclusions + dedupe (project > user)
# ---------------------------------------------------------------------------


def test_REQ_OSR_002_excluded_prefix_dropped(tmp_path: Path) -> None:
    """A skill named ``sdd-spec`` MUST NOT appear in the registry."""
    skills = tmp_path / "skills"
    _make_skill(skills, "sdd-spec", "excluded by prefix")
    _make_skill(skills, "chained-pr", "kept")

    refresh(tmp_path, source_dirs=[skills])
    registry = (tmp_path / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
    assert "sdd-spec" not in registry
    assert "chained-pr" in registry


def test_REQ_OSR_002_excluded_names_dropped(tmp_path: Path) -> None:
    """``_shared`` and ``skill-registry`` directories MUST NOT appear."""
    skills = tmp_path / "skills"
    _make_skill(skills, "_shared", "shared content")
    _make_skill(skills, "skill-registry", "registry doc")
    _make_skill(skills, "branch-pr", "kept")

    refresh(tmp_path, source_dirs=[skills])
    registry = (tmp_path / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
    assert "_shared" not in registry
    assert "skill-registry" not in registry
    assert "branch-pr" in registry


def test_REQ_OSR_002_project_beats_user_on_collision(tmp_path: Path) -> None:
    """When a name appears in both user and project scopes, ONLY the
    project-scoped version appears in the registry."""
    project_skills = tmp_path / "skills"
    user_skills = tmp_path / "user_skills"
    project_skill = _make_skill(project_skills, "chained-pr", "project version")
    _make_skill(user_skills, "chained-pr", "user version")

    refresh(tmp_path, project_dirs=[project_skills], user_dirs=[user_skills])
    registry = (tmp_path / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
    # Project entry's path is the only `chained-pr` row
    assert "project version" in registry
    assert "user version" not in registry
    # And its path resolves under the project root
    assert str(project_skill.relative_to(tmp_path)) in registry


# ---------------------------------------------------------------------------
# REQ-OSR-003 — Frontmatter parsing (success + warning)
# ---------------------------------------------------------------------------


def test_REQ_OSR_003_valid_frontmatter_includes_name_and_description(
    tmp_path: Path,
) -> None:
    """A SKILL.md with name + description frontmatter parses both."""
    skills = tmp_path / "skills"
    _make_skill(skills, "chained-pr", "Plan a stacked PR sequence.")

    result = refresh(tmp_path, source_dirs=[skills])
    registry = (tmp_path / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
    assert "| `chained-pr` | Plan a stacked PR sequence. | project |" in registry
    assert list(result.parse_warnings) == []


def test_REQ_OSR_003_missing_frontmatter_is_warning_not_crash(tmp_path: Path) -> None:
    """A SKILL.md without frontmatter records a parse warning; the
    registry still gets written and excludes the offending skill."""
    skills = tmp_path / "skills"
    bad = skills / "broken"
    bad.mkdir(parents=True)
    (bad / "SKILL.md").write_text("# No frontmatter here\n", encoding="utf-8")
    _make_skill(skills, "chained-pr", "kept")

    result = refresh(tmp_path, source_dirs=[skills])
    registry = (tmp_path / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
    # Registry still written
    assert result.changed is True
    assert "chained-pr" in registry
    # Warning surfaces
    assert any(str(bad / "SKILL.md") in w for w in result.parse_warnings)


# ---------------------------------------------------------------------------
# REQ-OSR-004 — match_skills lookup
# ---------------------------------------------------------------------------


def test_REQ_OSR_004_lookup_by_name_returns_skill(tmp_path: Path) -> None:
    """``match_skills(name="chained-pr")`` returns the discovered entry."""
    skills = tmp_path / "skills"
    target_path = _make_skill(skills, "chained-pr", "Plan a stacked PR sequence.")

    refresh(tmp_path, source_dirs=[skills])
    entries = [
        SkillEntry(
            name="chained-pr",
            path=target_path,
            description="Plan a stacked PR sequence.",
            source="project",
        )
    ]
    found = match_skills(entries, name="chained-pr")
    assert len(found) == 1
    assert found[0].path == target_path


def test_REQ_OSR_004_unknown_skill_raises_skill_not_found(tmp_path: Path) -> None:
    """``match_skills(name="does-not-exist")`` raises ``SkillNotFound``."""
    entries = []
    with pytest.raises(SkillNotFound):
        match_skills(entries, name="does-not-exist")


# ---------------------------------------------------------------------------
# REQ-OSR-005 — Atomic write
# ---------------------------------------------------------------------------


def test_REQ_OSR_005_atomic_write_replaces_registry(tmp_path: Path) -> None:
    """Refresh writes the registry via tmp + os.replace; the file is never
    truncated. Inspect: rename is atomic → registry exists with new content
    immediately after refresh()."""
    skills = tmp_path / "skills"
    _make_skill(skills, "chained-pr", "v1")
    refresh(tmp_path, source_dirs=[skills])

    # Change the skill content
    (skills / "chained-pr" / "SKILL.md").write_text(
        "---\nname: chained-pr\ndescription: v2 description.\n---\n\n# v2\n",
        encoding="utf-8",
    )

    # Refresh should detect the fingerprint changed and rewrite
    result = refresh(tmp_path, source_dirs=[skills])
    assert result.changed is True
    registry = (tmp_path / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
    assert "v2 description" in registry


# ---------------------------------------------------------------------------
# T1.18 — missing SOURCE_DIRS, output paths, content rendering, get_skill_paths
# ---------------------------------------------------------------------------


def test_REQ_OSR_missing_source_dirs_does_not_crash(tmp_path: Path) -> None:
    """Non-existent source dirs are skipped silently; the call still
    produces a valid (possibly empty) registry."""
    nonexistent = tmp_path / "nope"
    result = refresh(tmp_path, source_dirs=[nonexistent])
    assert result.changed is True
    assert (tmp_path / ".atl" / "skill-registry.md").exists()
    cache = json.loads(
        (tmp_path / ".atl" / ".skill-registry.cache.json").read_text(encoding="utf-8")
    )
    assert "fingerprint" in cache


def test_REQ_OSR_output_paths_under_dot_atl(tmp_path: Path) -> None:
    """Both outputs land under ``<root>/.atl/``."""
    skills = tmp_path / "skills"
    _make_skill(skills, "chained-pr", "ok")

    result = refresh(tmp_path, source_dirs=[skills])
    assert result.registry_path == tmp_path / ".atl" / "skill-registry.md"
    assert result.cache_path == tmp_path / ".atl" / ".skill-registry.cache.json"


def test_REQ_OSR_content_renders_skills_table(tmp_path: Path) -> None:
    """The markdown registry contains the ``## Skills`` section + a table
    with one row per skill including name, description (first sentence),
    scope, and path."""
    skills = tmp_path / "skills"
    _make_skill(skills, "chained-pr", "Plan a stacked PR sequence.")
    _make_skill(skills, "branch-pr", "Create PRs with issue-first checks.")

    refresh(tmp_path, source_dirs=[skills])
    registry = (tmp_path / ".atl" / "skill-registry.md").read_text(encoding="utf-8")
    assert "## Skills" in registry
    assert "| Skill |" in registry
    assert "| `chained-pr` | Plan a stacked PR sequence. | project |" in registry
    assert "| `branch-pr` | Create PRs with issue-first checks. | project |" in registry


def test_REQ_OSR_get_skill_paths_returns_discovered_paths(tmp_path: Path) -> None:
    """``get_skill_paths(root)`` is a non-destructive read that lists the
    SKILL.md files under the configured source dirs."""
    skills = tmp_path / "skills"
    a = _make_skill(skills, "chained-pr", "ok")
    b = _make_skill(skills, "branch-pr", "ok")

    paths = get_skill_paths(tmp_path, source_dirs=[skills])
    assert a in paths
    assert b in paths

"""Tests for opencontext_sdd.catalog (REQ: skills + agents + triggers catalog).

T1.19 -- ``test_catalog_lists_skills_agents_16_triggers_unique`` written FIRST.
"""

from __future__ import annotations

from opencontext_sdd.agents.registry import ADAPTERS
from opencontext_sdd.catalog import Catalog


def test_catalog_lists_skills_agents_16_triggers_unique(tmp_path) -> None:
    """Catalog must list skills, all ADAPTERS as agents, and unique triggers."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    catalog = Catalog.discover(
        root=tmp_path,
        skill_source_dirs=[skills_dir],
    )
    assert not catalog.skills  # empty skills dir => no SkillEntry rows
    assert len(catalog.agents) == len(ADAPTERS)
    assert all(a.id in ADAPTERS for a in catalog.agents)
    assert len(catalog.triggers) == len(set(catalog.triggers))

"""opencontext_sdd.catalog — Skills + agents + triggers catalog.

Single source of truth for the SDD orchestrator: skill entries from the
skill registry plus instantiated host-client adapters plus the union of
their identifiers as a deduped trigger list.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from opencontext_sdd.agents.registry import ADAPTERS
from opencontext_sdd.skill_registry import SkillEntry, get_skill_paths

if TYPE_CHECKING:
    from opencontext_sdd.agents.interface import Adapter


@dataclass(frozen=True)
class Catalog:
    """Frozen snapshot of skills + agents + unique triggers."""

    skills: tuple[SkillEntry, ...]
    agents: tuple[Adapter, ...]
    triggers: tuple[str, ...]

    @classmethod
    def discover(
        cls,
        *,
        root: str | Path,
        skill_source_dirs: list[Path] | None = None,
    ) -> Catalog:
        """Scan ``root`` for skills and instantiate every adapter in ADAPTERS."""
        root_path = Path(root).resolve()
        skills = tuple(_skill_entries(get_skill_paths(root_path, source_dirs=skill_source_dirs)))
        agents = tuple(_instantiate_adapters())
        triggers = tuple(sorted({s.name for s in skills} | set(ADAPTERS)))
        return cls(skills=skills, agents=agents, triggers=triggers)

    def agent_ids(self) -> tuple[str, ...]:
        """Registered agent ids in lexicographic order."""
        return tuple(sorted(ADAPTERS))

    def __post_init__(self) -> None:
        if len(self.triggers) != len(set(self.triggers)):
            raise ValueError("Catalog.triggers must be unique")


def _instantiate_adapters() -> list[Adapter]:
    """Instantiate one ``Adapter`` per registered class."""
    from opencontext_sdd.agents.interface import Adapter

    out: list[Adapter] = []
    for cls in ADAPTERS.values():
        inst = cls()
        if not isinstance(inst, Adapter):
            raise TypeError(f"{cls.__name__} does not satisfy Adapter protocol")
        out.append(inst)
    return out


def _skill_entries(paths: list[Path]) -> list[SkillEntry]:
    """Build ``SkillEntry`` records from raw ``SKILL.md`` paths (no I/O writes)."""
    from opencontext_sdd.skill_registry import _parse_frontmatter

    entries: list[SkillEntry] = []
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        frontmatter = _parse_frontmatter(content)
        name = str(frontmatter.get("name", "")).strip() or path.parent.name
        entries.append(
            SkillEntry(
                name=name,
                path=path,
                description=str(frontmatter.get("description", "")),
                source="project",
                fingerprint="",
            )
        )
    return entries


__all__ = ["Catalog"]

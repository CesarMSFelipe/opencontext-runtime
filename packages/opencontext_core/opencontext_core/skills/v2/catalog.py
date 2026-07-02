"""Skill v2 catalog — deterministic catalog generation + drift check (A6)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CatalogSkill:
    id: str
    name: str
    tier: int
    path: str


@dataclass(frozen=True)
class Catalog:
    skills: tuple[CatalogSkill, ...]

    def to_json(self) -> str:
        return json.dumps(
            {"skills": [s.__dict__ for s in self.skills]},
            sort_keys=True,
            indent=2,
        )


@dataclass(frozen=True)
class DriftReport:
    drifted: bool
    current: tuple[CatalogSkill, ...]
    committed: dict[str, Any] | None = None


def _catalog_path(root: Path) -> Path:
    return root / "catalog.json"


def generate_catalog(root: Path) -> Catalog:
    """Walk ``root`` for skill YAMLs and produce a deterministic :class:`Catalog`.

    Only files that declare an ``id`` key are treated as skill definitions.
    General project configs (e.g. ``opencontext.yaml``) are silently skipped,
    matching the discriminator used by :class:`~opencontext_core.skills.v2.audit.SkillAudit`.
    """
    skills: list[CatalogSkill] = []
    for yaml_file in sorted(root.glob("*.yaml")):
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            continue
        # Skip non-skill files (no 'id' key = general config, not a skill definition).
        if "id" not in data:
            continue
        skills.append(
            CatalogSkill(
                id=str(data.get("id", yaml_file.stem)),
                name=str(data.get("name", yaml_file.stem)),
                tier=int(data.get("tier", 0)),
                path=yaml_file.name,
            )
        )
    return Catalog(skills=tuple(skills))


def dry_run_update(root: Path) -> DriftReport:
    """Return whether the committed catalog is in sync with the live tree.

    Never writes — the actual write happens via the CLI's ``catalog generate``
    command. Used by the gate to keep CI honest without a side-effecting call.
    """
    current = generate_catalog(root)
    committed: dict[str, Any] | None = None
    cat_path = _catalog_path(root)
    if cat_path.exists():
        try:
            committed = json.loads(cat_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            committed = None
    if committed is None:
        return DriftReport(drifted=True, current=current.skills, committed=None)
    committed_ids = {s["id"] for s in committed.get("skills", [])}
    current_ids = {s.id for s in current.skills}
    drifted = committed_ids != current_ids
    return DriftReport(drifted=drifted, current=current.skills, committed=committed)


__all__ = ["Catalog", "CatalogSkill", "DriftReport", "dry_run_update", "generate_catalog"]

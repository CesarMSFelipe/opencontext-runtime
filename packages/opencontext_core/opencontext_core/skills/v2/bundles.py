"""Skill v2 bundles — load named workflow bundles from disk (A6)."""

from __future__ import annotations

from pathlib import Path

import yaml

from opencontext_core.skills.v2.bundle import SkillBundle, SkillTier


def load_bundle(name: str, *, root: Path) -> SkillBundle:
    """Load ``<root>/<name>.yaml`` and parse it as a :class:`SkillBundle`."""
    path = root / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"bundle not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # normalise the YAML shape → SkillBundle fields (the bundle YAML uses
    # audit-friendly keys like required_capabilities / persona_compat / contract
    # that the SkillBundle Pydantic model does not declare directly).
    data = dict(raw)
    data.setdefault("id", name)
    data.setdefault("name", name)
    tier_value = data.get("tier", 0)
    if not isinstance(tier_value, SkillTier):
        data["tier"] = SkillTier(f"tier{tier_value}")
    data.setdefault("profile", "balanced")
    data.setdefault("task", data.get("name", name))
    data.setdefault("workflow_id", name)
    # persona: prefer the first persona_compat entry, fall back to senior-architect
    personas = data.get("persona_compat") or []
    first_persona = personas[0] if personas else "senior-architect"
    data.setdefault("persona", first_persona)
    # gates: explicit gates first, else derived from required_capabilities
    if "gates" not in data:
        data["gates"] = data.get("required_capabilities", []) or []
    # inputs / outputs: derived from contract when present
    contract = data.get("contract") or {}
    data.setdefault("inputs", contract.get("inputs", {}) or {})
    data.setdefault("outputs", contract.get("outputs", []) or [])
    # drop the audit-friendly keys that the model does not accept
    for key in (
        "required_capabilities",
        "persona_compat",
        "contract",
    ):
        data.pop(key, None)
    return SkillBundle.model_validate(data)


__all__ = ["load_bundle"]

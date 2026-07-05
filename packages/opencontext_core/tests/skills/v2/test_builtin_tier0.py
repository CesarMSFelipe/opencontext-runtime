"""Tests for skills.builtins Tier 0 — must satisfy SkillAudit (A6)."""

from __future__ import annotations

from pathlib import Path

import yaml

BUILTINS_ROOT = Path(__file__).parents[3] / "opencontext_core" / "skills" / "builtins" / "core"


def test_first_run_skill_benchmark_executes() -> None:
    """The builtin Tier 0 set loads and each YAML declares tier=0."""
    yamls = sorted(BUILTINS_ROOT.glob("*.yaml"))
    assert yamls, f"no Tier 0 builtins under {BUILTINS_ROOT}"
    for yp in yamls:
        data = yaml.safe_load(yp.read_text(encoding="utf-8")) or {}
        assert data.get("tier") == 0, f"{yp.name} tier != 0"
        assert data.get("id"), f"{yp.name} missing id"

"""F1: Install agentic-flow flags (--preset/--memory/--budget/--openspec/--git) must
be reflected in the written opencontext.yaml, not silently ignored.

Strategy: test the pure YAML-patch helper directly (unit) and the _install()
integration path via subprocess (avoids the heavy mock wiring for the full
onboarding service).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Unit tests: _apply_agentic_flags_to_yaml helper (pure function, tested first)
# These are RED until the helper is extracted and wired into _install().
# ---------------------------------------------------------------------------


def _default_yaml(tmp_path: Path) -> dict:
    from opencontext_core.config import default_config_data

    data = default_config_data()
    (tmp_path / "opencontext.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )
    return data


def test_apply_flags_memory_engram(tmp_path: Path) -> None:
    """--memory engram must set memory.provider=engram in the YAML."""
    from opencontext_core.agentic.config import AgenticFlowConfig, MemoryMode
    from opencontext_cli.main import _apply_agentic_flags_to_yaml

    _default_yaml(tmp_path)
    cfg = AgenticFlowConfig(memory_mode=MemoryMode.ENGRAM)
    _apply_agentic_flags_to_yaml(tmp_path / "opencontext.yaml", cfg)

    result = yaml.safe_load((tmp_path / "opencontext.yaml").read_text(encoding="utf-8"))
    assert result["memory"]["provider"] == "engram", (
        f"expected memory.provider=engram; got {result.get('memory', {})}"
    )


def test_apply_flags_memory_local(tmp_path: Path) -> None:
    """--memory local must set memory.provider=local."""
    from opencontext_core.agentic.config import AgenticFlowConfig, MemoryMode
    from opencontext_cli.main import _apply_agentic_flags_to_yaml

    _default_yaml(tmp_path)
    cfg = AgenticFlowConfig(memory_mode=MemoryMode.LOCAL)
    _apply_agentic_flags_to_yaml(tmp_path / "opencontext.yaml", cfg)

    result = yaml.safe_load((tmp_path / "opencontext.yaml").read_text(encoding="utf-8"))
    assert result["memory"]["provider"] == "local"


def test_apply_flags_budget_strict(tmp_path: Path) -> None:
    """--budget strict must set context.budget_mode=strict."""
    from opencontext_core.agentic.config import AgenticFlowConfig, BudgetMode
    from opencontext_cli.main import _apply_agentic_flags_to_yaml

    _default_yaml(tmp_path)
    cfg = AgenticFlowConfig(budget_mode=BudgetMode.STRICT)
    _apply_agentic_flags_to_yaml(tmp_path / "opencontext.yaml", cfg)

    result = yaml.safe_load((tmp_path / "opencontext.yaml").read_text(encoding="utf-8"))
    assert result["context"]["budget_mode"] == "strict", (
        f"expected context.budget_mode=strict; got {result.get('context', {})}"
    )


def test_apply_flags_openspec_full(tmp_path: Path) -> None:
    """--openspec full must set sdd.artifact_store.mode != none."""
    from opencontext_core.agentic.config import AgenticFlowConfig, OpenSpecMode
    from opencontext_cli.main import _apply_agentic_flags_to_yaml

    _default_yaml(tmp_path)
    cfg = AgenticFlowConfig(openspec_mode=OpenSpecMode.FULL)
    _apply_agentic_flags_to_yaml(tmp_path / "opencontext.yaml", cfg)

    result = yaml.safe_load((tmp_path / "opencontext.yaml").read_text(encoding="utf-8"))
    mode = result.get("sdd", {}).get("artifact_store", {}).get("mode", "none")
    assert mode != "none", (
        f"expected sdd.artifact_store.mode != 'none' after --openspec full; got {mode!r}"
    )


def test_apply_flags_git_stacked_prs(tmp_path: Path) -> None:
    """--git stacked_prs must update sdd.delivery_strategy away from plan-only."""
    from opencontext_core.agentic.config import AgenticFlowConfig, GitMode
    from opencontext_cli.main import _apply_agentic_flags_to_yaml

    _default_yaml(tmp_path)
    cfg = AgenticFlowConfig(git_mode=GitMode.STACKED_PRS)
    _apply_agentic_flags_to_yaml(tmp_path / "opencontext.yaml", cfg)

    result = yaml.safe_load((tmp_path / "opencontext.yaml").read_text(encoding="utf-8"))
    delivery = result.get("sdd", {}).get("delivery_strategy", "plan-only")
    assert delivery != "plan-only", (
        f"expected sdd.delivery_strategy changed after --git stacked_prs; got {delivery!r}"
    )


def test_apply_flags_defaults_are_noop(tmp_path: Path) -> None:
    """An all-default AgenticFlowConfig must not alter the YAML (no-op)."""
    from opencontext_core.agentic.config import AgenticFlowConfig
    from opencontext_cli.main import _apply_agentic_flags_to_yaml

    _default_yaml(tmp_path)
    before = (tmp_path / "opencontext.yaml").read_text(encoding="utf-8")
    cfg = AgenticFlowConfig()  # all defaults
    _apply_agentic_flags_to_yaml(tmp_path / "opencontext.yaml", cfg)
    after = (tmp_path / "opencontext.yaml").read_text(encoding="utf-8")
    # YAML content must be unchanged (may reformat but keys must be identical)
    before_data = yaml.safe_load(before)
    after_data = yaml.safe_load(after)
    # Only keys touched by flags should differ; defaults = no-op means no diff.
    assert before_data.get("memory", {}).get("provider") == after_data.get("memory", {}).get("provider")
    assert before_data.get("context", {}).get("budget_mode") == after_data.get("context", {}).get("budget_mode")

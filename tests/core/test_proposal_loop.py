"""auto-improvement proposal loop.

Covers the side-effect-free proposal builder, the approve/apply/reject flow with
a reversible config delta, and the opt-in/bounded ``auto_improve`` config section.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from opencontext_core.config import default_config_data, load_config
from opencontext_core.learning.learning_orchestrator import LearningOrchestrator
from opencontext_core.learning.proposals import (
    ConfigProposal,
    ProposalEngine,
)


def _seed_budget_metrics(
    orch: LearningOrchestrator,
    *,
    operation_type: str = "context_pack",
    count: int = 20,
    used: int = 1000,
    budgeted: int = 8000,
) -> None:
    for _ in range(count):
        op_id = orch.start_operation(operation_type, "build context", tokens_budgeted=budgeted)
        orch.finish_operation(op_id, tokens_used=used, success=True)
    orch.learn()


def test_proposal_is_config_diff_shaped(tmp_path: Path) -> None:
    """A budget profile produces a config-diff-shaped proposal citing the metric."""
    orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=tmp_path / "kg.db")
    _seed_budget_metrics(orch)

    engine = ProposalEngine(orch)
    proposals = engine.build_proposals()

    assert proposals, "expected at least one budget proposal"
    budget_props = [p for p in proposals if "context_pack" in p.target_field]
    assert budget_props, "expected a context_pack budget proposal"
    p = budget_props[0]
    assert isinstance(p, ConfigProposal)
    assert p.target_field
    assert p.current_value is not None
    assert p.proposed_value is not None
    assert p.proposed_value != p.current_value
    # Rationale must cite the supporting metric (usage / efficiency).
    assert any(token in p.rationale.lower() for token in ("usage", "efficiency", "budget"))
    assert 0.0 <= p.confidence <= 1.0


def test_building_proposals_has_no_side_effects(tmp_path: Path) -> None:
    """Building proposals does not mutate config files or learned state."""
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(default_config_data(), sort_keys=False), encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")

    orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=tmp_path / "kg.db")
    _seed_budget_metrics(orch)

    engine = ProposalEngine(orch, config_path=config_path)
    engine.build_proposals()
    engine.build_proposals()  # idempotent

    assert config_path.read_text(encoding="utf-8") == before


def test_insufficient_evidence_yields_no_proposal(tmp_path: Path) -> None:
    """Fewer than the minimum observations yields no proposal for that op type."""
    orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=tmp_path / "kg.db")
    # Only 2 metrics — below the optimize_budgets gate of 3.
    _seed_budget_metrics(orch, count=2)

    engine = ProposalEngine(orch)
    proposals = engine.build_proposals()
    assert not [p for p in proposals if "context_pack" in p.target_field]


def test_approve_apply_writes_reversible_config_delta(tmp_path: Path) -> None:
    """Approving a proposal writes a config delta; backup makes it reversible."""
    config_path = tmp_path / "opencontext.yaml"
    data = default_config_data()
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=tmp_path / "kg.db")
    _seed_budget_metrics(orch)

    engine = ProposalEngine(orch, config_path=config_path)
    proposals = engine.build_proposals()
    p = next(pr for pr in proposals if "context_pack" in pr.target_field)

    outcome = engine.apply(p)
    assert outcome.applied is True
    assert outcome.backup_id, "apply must record a reversible backup id"

    # New config loads and reflects the proposed value as an applied budget.
    reloaded = load_config(config_path)
    assert reloaded.auto_improve.applied_budgets["context_pack"] == p.proposed_value

    # Reverting via the recorded backup restores the prior state.
    assert engine.revert(outcome) is True
    restored_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "context_pack" not in restored_data.get("auto_improve", {}).get("applied_budgets", {})


def test_reject_changes_nothing(tmp_path: Path) -> None:
    """Rejecting a proposal leaves config untouched and marks it rejected."""
    config_path = tmp_path / "opencontext.yaml"
    config_path.write_text(yaml.safe_dump(default_config_data(), sort_keys=False), encoding="utf-8")
    before = config_path.read_text(encoding="utf-8")

    orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=tmp_path / "kg.db")
    _seed_budget_metrics(orch)

    engine = ProposalEngine(orch, config_path=config_path)
    proposals = engine.build_proposals()
    p = proposals[0]

    engine.reject(p)
    assert config_path.read_text(encoding="utf-8") == before
    assert engine.is_rejected(p) is True


def test_auto_improve_disabled_by_default() -> None:
    """The auto_improve config section is disabled by default with policy=propose."""
    cfg = __import__(
        "opencontext_core.config", fromlist=["OpenContextConfig"]
    ).OpenContextConfig.model_validate(default_config_data())
    assert cfg.auto_improve.enabled is False
    assert cfg.auto_improve.apply_policy == "propose"
    assert cfg.auto_improve.max_auto_apply_per_cycle >= 1


def test_enable_flag_gates_auto_apply(tmp_path: Path) -> None:
    """Apply policy 'auto' but enabled=False applies zero proposals."""
    config_path = tmp_path / "opencontext.yaml"
    data = default_config_data()
    data["auto_improve"] = {"enabled": False, "apply_policy": "auto"}
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=tmp_path / "kg.db")
    _seed_budget_metrics(orch)

    engine = ProposalEngine(orch, config_path=config_path)
    applied, pending = engine.run_cycle()
    assert applied == []
    assert pending  # all retained as pending


def test_auto_policy_respects_per_cycle_bound(tmp_path: Path) -> None:
    """Apply policy 'auto' applies at most max_auto_apply_per_cycle proposals."""
    config_path = tmp_path / "opencontext.yaml"
    data = default_config_data()
    data["auto_improve"] = {
        "enabled": True,
        "apply_policy": "auto",
        "max_auto_apply_per_cycle": 1,
    }
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    orch = LearningOrchestrator(storage_path=tmp_path, kg_db_path=tmp_path / "kg.db")
    _seed_budget_metrics(orch, operation_type="context_pack")
    _seed_budget_metrics(orch, operation_type="ask")

    engine = ProposalEngine(orch, config_path=config_path)
    proposals = engine.build_proposals()
    assert len(proposals) >= 2, "test needs >1 proposal to exercise the bound"

    applied, pending = engine.run_cycle()
    assert len(applied) == 1
    assert len(pending) >= 1

"""Auto-improvement proposal builder and approval flow.

This module turns observed outcomes — learned ``TaskPattern``s, optimized
``TokenBudgetProfile``s, and ``TokenOptimizer.report_savings()`` — into
config-diff-shaped *proposals*. Building proposals is strictly side-effect-free:
no config, weight, or store is mutated as a result of inspecting learned data.

Behavior only changes through an explicit approval action:

* ``apply(proposal)`` writes a reversible config delta (a backup is recorded via
  the existing config-backup path before the new value is persisted).
* ``reject(proposal)`` changes nothing and marks the proposal rejected so the
  same proposal is not re-surfaced unchanged.

The ``auto_improve`` config section governs the whole flow: it is disabled by
default, exposes an ``apply_policy`` (``propose`` | ``auto``), and a per-cycle
bound so that even under ``auto`` at most N proposals are applied per cycle.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from opencontext_core.config import OpenContextConfig, default_config_data, load_config
from opencontext_core.learning.learning_orchestrator import LearningOrchestrator

# Minimum observations before a budget proposal is trustworthy. Mirrors the
# optimize_budgets gating (>= 3 metrics) plus the get_budget confidence gate.
_MIN_CONFIDENCE = 0.3


@dataclass
class ConfigProposal:
    """A config-diff-shaped, developer-approvable change suggestion."""

    target_field: str
    current_value: Any
    proposed_value: Any
    rationale: str
    confidence: float
    kind: str = "budget"

    @property
    def proposal_id(self) -> str:
        """Stable id derived from the target + values (rejection de-dup key)."""

        raw = f"{self.kind}:{self.target_field}:{self.current_value}->{self.proposed_value}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class ApplyOutcome:
    """Result of applying a proposal, carrying enough state to reverse it."""

    proposal: ConfigProposal
    applied: bool
    backup_id: str = ""
    prior_content: str = ""
    reason: str = ""
    _config_path: Path | None = field(default=None, repr=False)


class ProposalEngine:
    """Builds proposals from learned data and manages approve/apply/reject."""

    def __init__(
        self,
        orchestrator: LearningOrchestrator,
        config_path: str | Path | None = None,
    ) -> None:
        self._orch = orchestrator
        self._config_path = Path(config_path) if config_path is not None else None
        self._rejected: set[str] = set()

    # ── config helpers ───────────────────────────────────────────────────

    def _load_config(self) -> OpenContextConfig:
        if self._config_path is not None and self._config_path.exists():
            return load_config(self._config_path)
        return OpenContextConfig.model_validate(default_config_data())

    def _active_budget(self, config: OpenContextConfig, operation_type: str) -> int:
        applied = config.auto_improve.applied_budgets.get(operation_type)
        if applied is not None:
            return applied
        return config.context.max_input_tokens

    # ── build (side-effect-free) ─────────────────────────────────────────

    def build_proposals(self) -> list[ConfigProposal]:
        """Build config-diff-shaped proposals. Pure: no mutation of any state."""

        proposals: list[ConfigProposal] = []
        config = self._load_config()

        # Budget proposals from optimized TokenBudgetProfiles.
        budgets = self._orch.optimizer._budgets
        for op_type, profile in budgets.items():
            if profile.confidence < _MIN_CONFIDENCE:
                continue
            if profile.recommended_budget <= 0:
                continue
            current = self._active_budget(config, op_type)
            proposed = profile.recommended_budget
            if proposed == current:
                continue
            rationale = (
                f"Observed average usage for '{op_type}' is "
                f"{profile.avg_actual_usage} tokens (efficiency "
                f"{round(profile.efficiency_score, 2)}); recommend budget "
                f"{proposed} vs current {current}."
            )
            p = ConfigProposal(
                target_field=f"auto_improve.applied_budgets.{op_type}",
                current_value=current,
                proposed_value=proposed,
                rationale=rationale,
                confidence=round(profile.confidence, 4),
                kind="budget",
            )
            if p.proposal_id not in self._rejected:
                proposals.append(p)

        return proposals

    # ── reject (changes nothing) ─────────────────────────────────────────

    def reject(self, proposal: ConfigProposal) -> None:
        """Mark a proposal rejected. Does not touch config or weights."""

        self._rejected.add(proposal.proposal_id)

    def is_rejected(self, proposal: ConfigProposal) -> bool:
        return proposal.proposal_id in self._rejected

    # ── apply (reversible config delta) ──────────────────────────────────

    def apply(self, proposal: ConfigProposal) -> ApplyOutcome:
        """Apply a proposal as a reversible config delta.

        Records a backup (via the config-backup path) and snapshots prior file
        content before writing, so the change can be reverted. Returns an
        ``ApplyOutcome`` with ``applied=False`` (no mutation) when there is no
        config file path to write to.
        """

        if self._config_path is None:
            return ApplyOutcome(
                proposal=proposal,
                applied=False,
                reason="no_config_path",
            )

        path = self._config_path
        prior_content = path.read_text(encoding="utf-8") if path.exists() else ""

        # Reversible backup via the existing config-backup path (best-effort).
        backup_id = ""
        try:
            from opencontext_core.backup import BackupManager

            mgr = BackupManager(project_root=path.parent)
            info = mgr.create_backup(name=f"auto_improve_{proposal.proposal_id}")
            backup_id = info.id
        except Exception:
            backup_id = ""

        data: dict[str, Any] = {}
        if prior_content:
            loaded = yaml.safe_load(prior_content)
            if isinstance(loaded, dict):
                data = loaded
        if not data:
            data = default_config_data()

        self._write_proposal_value(data, proposal)
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

        # Fall back to a content-snapshot revert id when no backup was recorded.
        if not backup_id:
            backup_id = f"snapshot:{proposal.proposal_id}"

        return ApplyOutcome(
            proposal=proposal,
            applied=True,
            backup_id=backup_id,
            prior_content=prior_content,
            _config_path=path,
        )

    def _write_proposal_value(self, data: dict[str, Any], proposal: ConfigProposal) -> None:
        """Write the proposed value into the config dict at its target path."""

        parts = proposal.target_field.split(".")
        cursor: dict[str, Any] = data
        for key in parts[:-1]:
            child = cursor.get(key)
            if not isinstance(child, dict):
                child = {}
                cursor[key] = child
            cursor = child
        cursor[parts[-1]] = proposal.proposed_value

    def revert(self, outcome: ApplyOutcome) -> bool:
        """Reverse an applied proposal by restoring the prior config content."""

        if not outcome.applied:
            return False
        path = outcome._config_path or self._config_path
        if path is None:
            return False
        path.write_text(outcome.prior_content, encoding="utf-8")
        return True

    # ── cycle (policy + bound enforcement) ───────────────────────────────

    def run_cycle(self) -> tuple[list[ApplyOutcome], list[ConfigProposal]]:
        """Run one observe->propose->(maybe auto-apply) cycle.

        Returns ``(applied_outcomes, pending_proposals)``. Auto-apply happens
        only when the config enables it (``enabled=True`` AND
        ``apply_policy="auto"``), and never exceeds ``max_auto_apply_per_cycle``.
        Otherwise every proposal is returned as pending for developer review.
        """

        config = self._load_config()
        proposals = self.build_proposals()

        auto = config.auto_improve.enabled and config.auto_improve.apply_policy == "auto"
        if not auto:
            return [], proposals

        bound = config.auto_improve.max_auto_apply_per_cycle
        eligible = [p for p in proposals if p.confidence >= config.auto_improve.min_confidence]
        to_apply = eligible[:bound]
        applied = [self.apply(p) for p in to_apply]
        applied = [o for o in applied if o.applied]

        applied_ids = {o.proposal.proposal_id for o in applied}
        pending = [p for p in proposals if p.proposal_id not in applied_ids]
        return applied, pending


__all__ = [
    "ApplyOutcome",
    "ConfigProposal",
    "ProposalEngine",
]

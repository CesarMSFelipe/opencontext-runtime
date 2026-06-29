"""PR-004 REQ-10: HarnessRunner resume rehydrates prior-phase artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.run_store import RunStore
from opencontext_core.harness.runner import HarnessRunner


def _seed_prior_run(root: Path, prior_id: str) -> Path:
    """Write a prior run that completed explore+propose then stopped before spec."""
    prior_dir = root / ".opencontext" / "runs" / prior_id
    prior_dir.mkdir(parents=True, exist_ok=True)
    proposal_path = prior_dir / "proposal.json"
    proposal_path.write_text(
        json.dumps(
            {
                "run_id": prior_id,
                "task": "carryover task",
                "status": "drafted",
                "approach": {"method": "delegated"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (prior_dir / "events.json").write_text(
        json.dumps(
            {
                "events": [
                    {"phase": "explore", "action": "run_phase", "status": "passed"},
                    {"phase": "propose", "action": "run_phase", "status": "passed"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (prior_dir / "artifacts.json").write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "id": "proposal-x",
                        "phase": "propose",
                        "path": str(proposal_path),
                        "kind": "proposal",
                        "description": "prior proposal",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return proposal_path


def test_run_store_enumerates_passed_phase_artifacts(tmp_path: Path) -> None:
    prior_id = "sdd-prior000"
    proposal_path = _seed_prior_run(tmp_path, prior_id)
    files = RunStore(tmp_path).passed_phase_artifacts(prior_id, {"explore", "propose"})
    assert proposal_path in files


def test_resume_carries_proposal_forward_and_runs_spec(tmp_path: Path) -> None:
    prior_id = "sdd-prior000"
    _seed_prior_run(tmp_path, prior_id)

    runner = HarnessRunner(root=tmp_path)
    result = runner.run(
        "sdd", "carryover task", budget_mode=BudgetMode.OFF, resume_from=prior_id
    )

    new_dir = tmp_path / ".opencontext" / "runs" / result.run_id
    # The prior proposal.json was rehydrated into the resumed run dir...
    assert (new_dir / "proposal.json").exists()
    # ...so the spec phase found its input and ran to completion (spec.md written).
    assert (new_dir / "spec.md").exists()
    # explore + propose were skipped (recorded as skipped), spec executed.
    skipped = {e.phase for e in result.events if e.action == "skip_phase"}
    assert {"explore", "propose"} <= skipped
    spec_events = [e for e in result.events if e.phase == "spec" and e.action == "run_phase"]
    assert spec_events and spec_events[0].status in ("passed", "warning")
    assert result.status != GateStatus.FAILED

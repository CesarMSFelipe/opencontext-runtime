"""SDD-STATES / SDD-RULES — cycle state machine + operational status fields.

DOC1 §8 names the SDD cycle states (draft … archived, blocked, failed) and
requires `status --json` to report the current phase, gates, and next steps.
SDD_CONTRACT.md §State machine / §Status JSON are the authoritative shapes.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_sdd.status import Resolve


def _change_root(cwd: Path, change: str = "demo") -> Path:
    root = cwd / "openspec" / "changes" / change
    root.mkdir(parents=True, exist_ok=True)
    return root


def _state(cwd: Path, change: str = "demo") -> str:
    return Resolve(change, cwd=str(cwd)).cycleState


# ---------------------------------------------------------------------------
# SDD-STATES — state machine derivation from disk artifacts
# ---------------------------------------------------------------------------


def test_cycle_states_follow_artifact_progression(tmp_path: Path) -> None:
    """SDD-STATES: the resolver derives the cycle state machine position
    (draft → explored → proposed → specified → designed → applying → tasked)
    from the change's disk artifacts."""
    root = _change_root(tmp_path)
    assert _state(tmp_path) == "draft"

    (root / "exploration.md").write_text("# exploration\n", encoding="utf-8")
    assert _state(tmp_path) == "explored"

    (root / "proposal.md").write_text("# proposal\n", encoding="utf-8")
    assert _state(tmp_path) == "proposed"

    (root / "specs" / "cap").mkdir(parents=True)
    (root / "specs" / "cap" / "spec.md").write_text("# spec\n", encoding="utf-8")
    assert _state(tmp_path) == "specified"

    (root / "design.md").write_text("# design\n", encoding="utf-8")
    assert _state(tmp_path) == "designed"

    (root / "tasks.md").write_text("- [ ] one\n", encoding="utf-8")
    assert _state(tmp_path) == "applying"

    (root / "tasks.md").write_text("- [x] one\n", encoding="utf-8")
    assert _state(tmp_path) == "tasked"


def test_cycle_state_verified_then_reviewed(tmp_path: Path) -> None:
    """SDD-STATES: a passing verify-report moves the cycle to 'verified'; a
    review-report on top moves it to 'reviewed'."""
    root = _change_root(tmp_path)
    (root / "proposal.md").write_text("# proposal\n", encoding="utf-8")
    (root / "specs" / "cap").mkdir(parents=True)
    (root / "specs" / "cap" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (root / "design.md").write_text("# design\n", encoding="utf-8")
    (root / "tasks.md").write_text("- [x] one\n", encoding="utf-8")
    (root / "verify-report.md").write_text("verdict: PASS\n", encoding="utf-8")
    assert _state(tmp_path) == "verified"

    (root / "review-report.json").write_text("{}", encoding="utf-8")
    assert _state(tmp_path) == "reviewed"


def test_cycle_state_failed_on_failing_verify(tmp_path: Path) -> None:
    """SDD-STATES: a FAIL verify-report puts the cycle in the exception state
    'failed' (apply/verify gates failed)."""
    root = _change_root(tmp_path)
    (root / "proposal.md").write_text("# proposal\n", encoding="utf-8")
    (root / "specs" / "cap").mkdir(parents=True)
    (root / "specs" / "cap" / "spec.md").write_text("# spec\n", encoding="utf-8")
    (root / "design.md").write_text("# design\n", encoding="utf-8")
    (root / "tasks.md").write_text("- [x] one\n", encoding="utf-8")
    (root / "verify-report.md").write_text("verdict: FAIL\n- test_one\n", encoding="utf-8")
    assert _state(tmp_path) == "failed"


def test_cycle_state_blocked_for_missing_change(tmp_path: Path) -> None:
    """SDD-STATES: a missing change dir resolves to the exception state 'blocked'."""
    (tmp_path / "openspec" / "changes").mkdir(parents=True)
    status = Resolve("ghost", cwd=str(tmp_path))
    assert status.cycleState == "blocked"


def test_forward_only_chain_blocks_phase_skips(tmp_path: Path) -> None:
    """SDD-STATES: transitions are forward-only — the phase runner blocks a
    request that skips a missing predecessor and names the expected phase."""
    from opencontext_sdd.runner import run_phase

    root = _change_root(tmp_path)
    (root / "proposal.md").write_text("# proposal\n", encoding="utf-8")

    envelope = run_phase("design", change="demo", cwd=str(tmp_path))
    assert envelope.status == "blocked"
    assert envelope.next_recommended == "spec"
    assert "must complete first" in envelope.executive_summary


# ---------------------------------------------------------------------------
# SDD-RULES — status --json reports current phase, gates, and next steps
# ---------------------------------------------------------------------------


def test_status_json_exposes_current_phase_gates_and_next_steps(tmp_path: Path) -> None:
    """SDD-RULES: `status --json` reports the current phase, the latest harness
    run's gates, and the next recommended step."""
    root = _change_root(tmp_path)
    (root / "proposal.md").write_text("# proposal\n", encoding="utf-8")
    (root / "specs" / "cap").mkdir(parents=True)
    (root / "specs" / "cap" / "spec.md").write_text("# spec\n", encoding="utf-8")

    run_dir = tmp_path / ".opencontext" / "runs" / "sdd-abc123"
    run_dir.mkdir(parents=True)
    (run_dir / "gates.json").write_text(
        json.dumps(
            {
                "gates": [
                    {
                        "id": "verify_tests_passed",
                        "phase": "verify",
                        "status": "failed",
                        "message": "Tests exited with code 1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    status = Resolve("demo", cwd=str(tmp_path))
    payload = json.loads(status.model_dump_json())
    assert payload["currentPhase"] == "spec"
    assert payload["nextRecommended"] == "design"
    assert payload["gates"], "status must surface the latest run's gates"
    assert payload["gates"][0]["id"] == "verify_tests_passed"
    assert payload["gates"][0]["status"] == "failed"
    assert payload["gatesRun"] == "sdd-abc123"


def test_status_gates_empty_without_runs(tmp_path: Path) -> None:
    """SDD-RULES: with no harness runs on disk `status --json` reports an empty
    gates list — evidence is never fabricated."""
    root = _change_root(tmp_path)
    (root / "proposal.md").write_text("# proposal\n", encoding="utf-8")

    status = Resolve("demo", cwd=str(tmp_path))
    payload = json.loads(status.model_dump_json())
    assert payload["gates"] == []
    assert payload["currentPhase"] == "propose"

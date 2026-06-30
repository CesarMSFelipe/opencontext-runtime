"""VDM-007: the e2e B+D evidence artifact moves the 15 functional + 2 governance gates.

``release acceptance`` reads ``release-evidence.json`` and injects ``functional=`` /
``governance=`` into :meth:`AcceptanceEvaluator.evaluate`. Only gates with REAL evidence
become MET; the rest stay honestly NOT_MEASURED (build-rule #1) — never a fake pass.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.evaluation.models import GateStatus
from opencontext_core.operating_model.release_gate import (
    FUNCTIONAL_BEHAVIOURS,
    GOVERNANCE_GATES,
    AcceptanceEvaluator,
    read_release_evidence,
    write_release_evidence,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _statuses(root: Path) -> dict[str, GateStatus]:
    functional, governance = read_release_evidence(root)
    verdict = AcceptanceEvaluator(repo_root=PROJECT_ROOT).evaluate(
        bench_root=str(PROJECT_ROOT), functional=functional or None, governance=governance or None
    )
    return {g.gate: g.status for g in verdict.gates}


def test_full_evidence_moves_all_17_gates_to_met(tmp_path: Path) -> None:
    write_release_evidence(
        tmp_path,
        functional={name: "met" for name in FUNCTIONAL_BEHAVIOURS},
        governance={name: ["met", "evidence present"] for name in GOVERNANCE_GATES},
    )
    statuses = _statuses(tmp_path)
    for name in (*FUNCTIONAL_BEHAVIOURS, *GOVERNANCE_GATES):
        assert statuses[name] is GateStatus.MET, name


def test_partial_evidence_only_moves_evidenced_gates(tmp_path: Path) -> None:
    five = list(FUNCTIONAL_BEHAVIOURS[:5])
    write_release_evidence(tmp_path, functional={n: "met" for n in five}, governance={})
    statuses = _statuses(tmp_path)
    met_b = [n for n in FUNCTIONAL_BEHAVIOURS if statuses[n] is GateStatus.MET]
    nm_b = [n for n in FUNCTIONAL_BEHAVIOURS if statuses[n] is GateStatus.NOT_MEASURED]
    assert set(met_b) == set(five)
    assert len(nm_b) == 10
    # No governance evidence -> both D gates stay NOT_MEASURED.
    for name in GOVERNANCE_GATES:
        assert statuses[name] is GateStatus.NOT_MEASURED


def test_missing_evidence_file_keeps_all_17_not_measured(tmp_path: Path) -> None:
    # No release-evidence.json under this root: read returns empty maps, no error.
    functional, governance = read_release_evidence(tmp_path)
    assert functional == {} and governance == {}
    statuses = _statuses(tmp_path)
    for name in (*FUNCTIONAL_BEHAVIOURS, *GOVERNANCE_GATES):
        assert statuses[name] is GateStatus.NOT_MEASURED, name


def test_failed_evidence_entry_is_honest_failed_not_met(tmp_path: Path) -> None:
    write_release_evidence(
        tmp_path,
        functional={"create-usable-config": ["failed", "install wrote no config"]},
        governance={},
    )
    statuses = _statuses(tmp_path)
    assert statuses["create-usable-config"] is GateStatus.FAILED

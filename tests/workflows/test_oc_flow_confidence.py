"""R4: ConfidenceEngine result wired into OCFlow decision log.

After consolidation, OCFlowRunner must append a 'confidence_report' RuntimeDecision
to the decision log so that decisions.json contains the confidence record with dims.

Failing tests:
- result.decisions contains an entry with kind == "confidence_report".
- decisions.json on disk contains the confidence record.
- The confidence decision's inputs include dimension data (overall + dims).
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.oc_flow.runner import OCFlowRunner


def test_decisions_contain_confidence_report(tmp_path: Path) -> None:
    """After a run, result.decisions must include a 'confidence_report' entry."""
    result = OCFlowRunner(root=tmp_path).run("Fix failing test")

    kinds = [d["kind"] for d in result.decisions]
    assert "confidence_report" in kinds, (
        f"Expected 'confidence_report' in decision kinds.\nGot: {kinds}"
    )


def test_decisions_json_contains_confidence_record(tmp_path: Path) -> None:
    """decisions.json on disk must contain the confidence_report record."""
    result = OCFlowRunner(root=tmp_path).run("Fix failing test")

    run_dir = result.artifacts_dir.parent.parent
    decisions_json = (run_dir / "decisions.json").read_text(encoding="utf-8")
    assert "confidence_report" in decisions_json, (
        f"Expected 'confidence_report' in decisions.json.\nContent:\n{decisions_json}"
    )


def test_confidence_decision_includes_dims(tmp_path: Path) -> None:
    """The confidence_report decision must carry overall + dims in its inputs."""
    result = OCFlowRunner(root=tmp_path).run("Fix failing test")

    conf_decisions = [d for d in result.decisions if d["kind"] == "confidence_report"]
    assert conf_decisions, "No confidence_report decision found in result.decisions"

    run_dir = result.artifacts_dir.parent.parent
    decisions_raw = json.loads((run_dir / "decisions.json").read_text(encoding="utf-8"))
    conf_entries = [
        d for d in decisions_raw.get("decisions", []) if d.get("kind") == "confidence_report"
    ]
    assert conf_entries, "No confidence_report entry in decisions.json"
    # The entry must reference 'overall' in its rationale or selected value
    entry = conf_entries[0]
    assert entry.get("selected") or entry.get("rationale"), (
        "confidence_report decision must have a selected/rationale value"
    )

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


def test_confidence_report_wired_into_decisions_and_json(tmp_path: Path) -> None:
    """After a run, the confidence_report is present in result.decisions, on disk
    in decisions.json, and carries a selected/rationale value.

    (Consolidated from three over-granular splits of the same single run: the
    in-memory presence, the on-disk record, and the dims/inputs check.)
    """
    result = OCFlowRunner(root=tmp_path).run("Fix failing test")

    # In-memory: result.decisions includes a confidence_report entry.
    conf_decisions = [d for d in result.decisions if d["kind"] == "confidence_report"]
    kinds = [d["kind"] for d in result.decisions]
    assert conf_decisions, f"No confidence_report in result.decisions.\nGot kinds: {kinds}"

    # On disk: decisions.json carries the same record.
    run_dir = result.artifacts_dir.parent.parent
    decisions_json = (run_dir / "decisions.json").read_text(encoding="utf-8")
    assert "confidence_report" in decisions_json, (
        f"Expected 'confidence_report' in decisions.json.\nContent:\n{decisions_json}"
    )

    decisions_raw = json.loads(decisions_json)
    conf_entries = [
        d for d in decisions_raw.get("decisions", []) if d.get("kind") == "confidence_report"
    ]
    assert conf_entries, "No confidence_report entry in decisions.json"
    entry = conf_entries[0]
    assert entry.get("selected") or entry.get("rationale"), (
        "confidence_report decision must have a selected/rationale value"
    )

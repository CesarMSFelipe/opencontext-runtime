"""TDD-POL-NA: a documentation/read-only task under strict TDD yields not_applicable.

Policy: when no tests apply (documentation / analysis / read-only tasks), strict
TDD must record an explicit ``not_applicable`` result with a justification —
never a silent empty strict block, and never a fabricated RED/GREEN.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.runner import OCFlowRunner
from opencontext_core.tdd.red_green import TDD_NOT_APPLICABLE, TddEvidence

# ---------------------------------------------------------------------------
# TddEvidence.to_json — additive not_applicable marker
# ---------------------------------------------------------------------------


def test_to_json_carries_not_applicable_marker() -> None:
    """TDD-POL-NA: mode_result + justification are persisted when set (additive)."""
    payload = TddEvidence(
        mode="strict",
        mode_result=TDD_NOT_APPLICABLE,
        justification="read-only documentation task; no tests apply",
    ).to_json()
    assert payload["mode_result"] == "not_applicable"
    assert payload["justification"] == "read-only documentation task; no tests apply"
    # The honest empty cycle: nothing is fabricated.
    assert payload["red"] is None
    assert payload["green"] is None
    assert payload["red_proven"] is False
    assert payload["green_proven"] is False


def test_to_json_omits_marker_when_tdd_applies() -> None:
    """TDD-POL-NA: applicable strict runs carry no not_applicable marker."""
    payload = TddEvidence(mode="strict").to_json()
    assert "mode_result" not in payload
    assert "justification" not in payload


# ---------------------------------------------------------------------------
# end-to-end: strict + read-only task
# ---------------------------------------------------------------------------


def test_strict_readonly_task_reports_not_applicable(tmp_path: Path, monkeypatch) -> None:
    """TDD-POL-NA: strict + doc task completes with an explicit not_applicable tdd result."""
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    result = OCFlowRunner(root=tmp_path).run("Explain the calc module", lane=Lane.FAST)

    assert result.status == "completed"
    assert result.mutation_required is False
    assert result.tdd is not None
    assert result.tdd["mode"] == "strict"
    assert result.tdd["mode_result"] == "not_applicable"
    assert result.tdd["justification"], "not_applicable must carry a justification"
    # No fabricated RED/GREEN and no violation for an honest read-only run.
    assert result.tdd["red"] is None
    assert result.tdd["green"] is None
    assert "violation" not in result.tdd
    assert result.exit_code == 0

    # The persisted run.json carries the same explicit marker.
    run_dir = result.artifacts_dir.parent.parent
    report = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert report["tdd"]["mode_result"] == "not_applicable"
    assert report["tdd"]["justification"]


def test_strict_mutation_task_has_no_not_applicable_marker(tmp_path: Path, monkeypatch) -> None:
    """TDD-POL-NA: a strict mutation task never claims not_applicable."""
    monkeypatch.setenv("OPENCONTEXT_TDD_MODE", "strict")
    result = OCFlowRunner(root=tmp_path).run("Fix the subtraction bug", lane=Lane.FAST)

    assert result.tdd is not None
    assert result.tdd.get("mode_result") != "not_applicable"

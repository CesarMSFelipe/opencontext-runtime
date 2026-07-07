"""TDD — C16: RuntimeDecision emissions at real selection sites.

RED gate: runner.py currently emits only kind="next_node" decisions.
The test asserts that decisions.json from a real run contains >1 distinct kind
including "workflow" (workflow selection) and "memory_promotion" (consolidation
verdict), which fails until runner.py emits decisions at those sites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.runner import OCFlowRunner


def test_decisions_json_has_multiple_kinds(tmp_path: Path) -> None:
    """A real run must emit >1 distinct kind in decisions.json."""
    runner = OCFlowRunner(tmp_path)
    result = runner.run("Describe the project layout", lane=Lane.FAST)

    # Locate the run directory from session/run ids
    session_dir = (
        Path(tmp_path) / ".opencontext" / "sessions" / result.session_id / "runs" / result.run_id
    )
    decisions_path = session_dir / "decisions.json"
    assert decisions_path.exists(), f"decisions.json not found at {decisions_path}"

    data = json.loads(decisions_path.read_text(encoding="utf-8"))
    decisions = data.get("decisions", [])
    assert decisions, "decisions.json must contain at least one entry"

    kinds = {d["kind"] for d in decisions}
    assert len(kinds) > 1, f"Expected >1 distinct kind, got: {kinds}"
    assert "workflow" in kinds, f"Expected 'workflow' kind in decisions, got: {kinds}"
    assert "memory_promotion" in kinds, (
        f"Expected 'memory_promotion' kind in decisions, got: {kinds}"
    )


def test_workflow_decision_has_required_fields(tmp_path: Path) -> None:
    """The workflow decision must carry chosen (oc-flow|sdd) and a reason string."""
    runner = OCFlowRunner(tmp_path)
    result = runner.run("Fix a bug in utils.py", lane=Lane.FAST)

    session_dir = (
        Path(tmp_path) / ".opencontext" / "sessions" / result.session_id / "runs" / result.run_id
    )
    data = json.loads((session_dir / "decisions.json").read_text(encoding="utf-8"))
    workflow_decisions = [d for d in data["decisions"] if d["kind"] == "workflow"]
    assert workflow_decisions, "At least one 'workflow' decision must be present"
    wd = workflow_decisions[0]
    assert wd.get("selected") in ("oc-flow", "sdd"), (
        f"workflow decision 'selected' must be 'oc-flow' or 'sdd', got: {wd.get('selected')}"
    )
    assert wd.get("rationale"), "workflow decision must carry a rationale"


def test_memory_promotion_decision_present(tmp_path: Path) -> None:
    """The memory_promotion decision must appear after consolidation."""
    runner = OCFlowRunner(tmp_path)
    result = runner.run("Summarize repo", lane=Lane.FAST)

    session_dir = (
        Path(tmp_path) / ".opencontext" / "sessions" / result.session_id / "runs" / result.run_id
    )
    data = json.loads((session_dir / "decisions.json").read_text(encoding="utf-8"))
    promo = [d for d in data["decisions"] if d["kind"] == "memory_promotion"]
    assert promo, "memory_promotion decision must be recorded by consolidation"
    # A no-op run with no changes and no inspection → not_promoted
    assert promo[0]["selected"] in ("promote", "reject", "keep", "not_promoted"), (
        f"memory_promotion selected must be a verdict string, got: {promo[0]['selected']}"
    )


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

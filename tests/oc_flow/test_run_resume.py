"""`run --resume` restores the prior run instead of starting a new one.

Regression: the --resume flag was accepted but ignored — handle_run_exec always
started a fresh run. It now restores via OCFlowRunner.resume, which returns the
same session/run and its apply receipts.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.runner import OCFlowRunner


def test_resume_restores_same_run(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    edit = ApplyEdit(
        path="calc.py",
        operation=ApplyOperation.REPLACE_RANGE,
        start_line=2,
        end_line=2,
        content="    return a + b",
        reason="fix",
        requirement_refs=["sum"],
    )
    runner = OCFlowRunner(root=tmp_path)
    original = runner.run("fix add", lane=Lane.FAST, requested_edits=[edit])

    resumed = runner.resume(original.session_id, original.run_id)

    assert resumed.session_id == original.session_id
    assert resumed.run_id == original.run_id
    changed = [r.get("path") for r in resumed.apply_receipts.get("receipts", [])]
    assert "calc.py" in changed

"""OC Flow apply receipts record before/after checksums.

Regression: node_mutate wrote receipts (path/operation/changed) with no
checksums, so a receipt could not prove what bytes it changed. It now records
sha256 checksum_before (from the rollback checkpoint) and checksum_after.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.runner import OCFlowRunner


def test_apply_receipt_records_checksums(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    edit = ApplyEdit(
        path="calc.py",
        operation=ApplyOperation.REPLACE_RANGE,
        start_line=2,
        end_line=2,
        content="    return a + b",
        reason="fix the operator",
        requirement_refs=["add returns the sum"],
    )

    result = OCFlowRunner(root=tmp_path).run("fix add", lane=Lane.FAST, requested_edits=[edit])

    receipts_files = list((tmp_path / ".opencontext").rglob("apply-receipts.json"))
    assert receipts_files, "no apply-receipts.json written"
    receipts = json.loads(receipts_files[0].read_text(encoding="utf-8"))["receipts"]
    assert receipts, "no receipts recorded"
    rec = receipts[0]
    assert rec["path"] == "calc.py"
    assert rec.get("checksum_before") and len(rec["checksum_before"]) == 64
    assert rec.get("checksum_after") and len(rec["checksum_after"]) == 64
    assert rec["checksum_before"] != rec["checksum_after"]
    assert result is not None


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

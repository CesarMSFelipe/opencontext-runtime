"""persist_run emits a consolidated harness-report.json.

Regression: harness-report.json was declared as a verify required_output but had
no writer, so it never appeared on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.runner import HarnessRunner


def test_persist_run_writes_harness_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    result = HarnessRunner(root=tmp_path).run("sdd", "add a helper")

    reports = list((tmp_path / ".opencontext" / "runs").rglob("harness-report.json"))
    assert reports, "harness-report.json was not written"
    data = json.loads(reports[0].read_text(encoding="utf-8"))
    assert data["run_id"] == result.run_id
    assert data["workflow"] == "sdd"
    assert "status" in data
    assert "by_status" in data["gates"]
    assert isinstance(data["phases"], list)

"""Secrets in the task must be redacted before persistence (security).

Regression for a verification finding: a token pasted into the run task was
persisted RAW into ~10 run artifacts, including the provider-bound
context-envelope.json — contradicting "Context redaction is applied
automatically". The task is now redacted at the flow boundary.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.runner import OCFlowRunner

_SECRET = "sk-SECRET1234567890ABCDEFtest"


def test_task_secret_is_redacted_in_all_run_artifacts(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    OCFlowRunner(root=tmp_path).run(f"fix add; token {_SECRET}", lane=Lane.FAST)

    artifacts = list((tmp_path / ".opencontext").rglob("*")) + list(
        (tmp_path / ".storage").rglob("*")
    )
    leaked = [
        p
        for p in artifacts
        if p.is_file() and _SECRET in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not leaked, f"raw secret leaked into: {[str(p) for p in leaked]}"

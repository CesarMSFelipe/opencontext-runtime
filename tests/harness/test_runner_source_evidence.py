"""Harness verification evidence records runner_source (additive field).

The tests_pass gate resolves the verification command through
``resolve_test_command`` and stamps the chosen source on its metadata; the
run.json ``tdd`` block carries it forward as ``runner_source``.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.models import GateStatus, PhaseGate
from opencontext_core.harness.runner import HarnessRunner


def test_tdd_block_carries_runner_source(tmp_path: Path) -> None:
    runner = HarnessRunner(root=tmp_path)
    gates = [
        PhaseGate(
            id="tests_pass",
            phase="verify",
            status=GateStatus.PASSED,
            message="green",
            metadata={
                "command": "python -m pytest -q",
                "exit_code": 0,
                "runner_source": "project_venv",
            },
        )
    ]

    block = runner._tdd_block_from_gates(gates, created_at="2026-01-01T00:00:00+00:00")

    assert block is not None
    assert block["green"]["runner_source"] == "project_venv"
    assert block["green_proven"] is True

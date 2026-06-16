"""Honest ApplyPhase contract tests (, task 3.1).

ApplyPhase must EITHER:
  - apply real executor edits (changed files listed, content actually written), OR
  - report ``status="planned"`` with ZERO filesystem mutation.

It must NEVER report ``status="applied"`` over an empty ``changes`` list.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import ApplyPhase
from opencontext_core.harness.runner import HarnessRunner


def _read_manifest(phase_result: object) -> dict:
    manifest_path = Path(phase_result.artifacts[0].path)  # type: ignore[attr-defined]
    return json.loads(manifest_path.read_text(encoding="utf-8"))


class TestApplyPhaseHonest:
    def test_no_edits_yields_planned_and_no_mutation(self, tmp_path: Path) -> None:
        # A source file that must remain byte-identical when no edits are applied.
        src = tmp_path / "module.py"
        src.write_text("original = 1\n", encoding="utf-8")
        before = src.read_text(encoding="utf-8")

        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "no edits task")
        cfg = runner.config.phases.get("apply")
        phase = ApplyPhase(cfg, BudgetMode.OFF)
        phase_result = phase.run(state)

        manifest = _read_manifest(phase_result)
        # Honest contract: planned, not applied, when nothing was written.
        assert manifest["status"] == "planned"
        assert manifest["changes"] == []
        # No source file mutated.
        assert src.read_text(encoding="utf-8") == before

    def test_never_reports_applied_over_empty_changes(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "empty apply")
        cfg = runner.config.phases.get("apply")
        phase = ApplyPhase(cfg, BudgetMode.OFF)
        manifest = _read_manifest(phase.run(state))
        assert not (manifest["status"] == "applied" and not manifest["changes"])

    def test_concrete_edits_are_applied_and_recorded(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "feature.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def feature():\n    return 0\n", encoding="utf-8")

        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "real edit task")
        # The executor produced a concrete edit for this run.
        state.apply_edits = [{"path": str(target), "content": "def feature():\n    return 42\n"}]
        cfg = runner.config.phases.get("apply")
        phase = ApplyPhase(cfg, BudgetMode.OFF)
        phase_result = phase.run(state)

        manifest = _read_manifest(phase_result)
        assert manifest["status"] == "applied"
        assert phase_result.status == GateStatus.PASSED
        paths = [c["path"] for c in manifest["changes"]]
        assert str(target) in paths
        # The edit was actually written to disk.
        assert target.read_text(encoding="utf-8") == "def feature():\n    return 42\n"

    def test_new_file_creation_is_applied(self, tmp_path: Path) -> None:
        new_file = tmp_path / "pkg" / "created.py"

        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "create file task")
        state.apply_edits = [{"path": str(new_file), "content": "X = 1\n"}]
        cfg = runner.config.phases.get("apply")
        phase = ApplyPhase(cfg, BudgetMode.OFF)
        manifest = _read_manifest(phase.run(state))

        assert manifest["status"] == "applied"
        assert new_file.exists()
        assert new_file.read_text(encoding="utf-8") == "X = 1\n"

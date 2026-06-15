"""Checkpoint-backed rollback around ApplyPhase writes.

A write becomes: snapshot -> apply -> (on gate/approval failure or error)
restore. A forced post-apply failure MUST roll the workspace back to the
checkpoint so the captured files are byte-identical to before the apply, and the
phase must not report a successful apply.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import ApplyPhase
from opencontext_core.harness.runner import HarnessRunner


def _manifest(phase_result: object) -> dict:
    path = Path(phase_result.artifacts[0].path)  # type: ignore[attr-defined]
    return json.loads(path.read_text(encoding="utf-8"))


class TestApplyCheckpointRollback:
    def test_post_apply_failure_rolls_back_to_checkpoint(self, tmp_path: Path) -> None:
        existing = tmp_path / "existing.py"
        existing.write_bytes(b"ORIGINAL\n")
        new_file = tmp_path / "new.py"  # absent before apply

        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "checkpoint rollback")
        state.apply_edits = [
            {"path": str(existing), "content": "MODIFIED\n"},
            {"path": str(new_file), "content": "CREATED\n"},
        ]
        cfg = runner.config.phases.get("apply")

        # A forced post-apply gate failure (e.g. a security gate that rejects the
        # write). The write succeeds, then the verifier fails -> rollback.
        phase = ApplyPhase(cfg, BudgetMode.OFF, verify_after_apply=lambda _changes: False)
        result = phase.run(state)

        # Workspace restored byte-identical to before the apply.
        assert existing.read_bytes() == b"ORIGINAL\n"
        assert not new_file.exists()
        # Phase did not report a successful apply.
        assert result.status == GateStatus.FAILED
        assert _manifest(result)["status"] != "applied"

    def test_successful_verify_keeps_changes(self, tmp_path: Path) -> None:
        target = tmp_path / "keep.py"
        target.write_bytes(b"OLD\n")

        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "checkpoint keep")
        state.apply_edits = [{"path": str(target), "content": "NEW\n"}]
        cfg = runner.config.phases.get("apply")

        phase = ApplyPhase(cfg, BudgetMode.OFF, verify_after_apply=lambda _changes: True)
        result = phase.run(state)

        assert target.read_bytes() == b"NEW\n"
        assert result.status == GateStatus.PASSED
        assert _manifest(result)["status"] == "applied"

    def test_default_apply_still_writes_without_verifier(self, tmp_path: Path) -> None:
        target = tmp_path / "plain.py"
        target.write_bytes(b"OLD\n")

        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "plain apply")
        state.apply_edits = [{"path": str(target), "content": "NEW\n"}]
        cfg = runner.config.phases.get("apply")

        phase = ApplyPhase(cfg, BudgetMode.OFF)
        result = phase.run(state)

        assert target.read_bytes() == b"NEW\n"
        assert result.status == GateStatus.PASSED
        assert _manifest(result)["status"] == "applied"
        # The checkpoint that guarded the write is recorded for inspection.
        assert result.metadata.get("checkpoint_id")

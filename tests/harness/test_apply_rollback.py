"""ApplyPhase rollback test (, task 3.4).

A mid-apply executor failure MUST restore ALL touched files to their
pre-apply state (no partial application).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import ApplyPhase, CodeEditExecutor, FileEdit
from opencontext_core.harness.runner import HarnessRunner


class TestCodeEditExecutorRollback:
    def test_mid_apply_failure_restores_all_touched_files(self, tmp_path: Path) -> None:
        a = tmp_path / "a.py"
        b = tmp_path / "b.py"
        a.write_text("A0\n", encoding="utf-8")
        b.write_text("B0\n", encoding="utf-8")

        executor = CodeEditExecutor(tmp_path)
        # The second edit raises during write (directory collision), forcing rollback.
        bad_dir = tmp_path / "c.py"
        bad_dir.mkdir()  # make c.py an existing directory -> writing a file there fails

        edits = [
            FileEdit(path=str(a), content="A1\n"),
            FileEdit(path=str(b), content="B1\n"),
            FileEdit(path=str(bad_dir), content="C1\n"),
        ]

        # Writing to a path that is an existing directory raises IsADirectoryError.
        with pytest.raises(OSError):
            executor.apply(edits)

        # All previously-touched files restored to pre-apply content.
        assert a.read_text(encoding="utf-8") == "A0\n"
        assert b.read_text(encoding="utf-8") == "B0\n"

    def test_rollback_removes_newly_created_files(self, tmp_path: Path) -> None:
        existing = tmp_path / "exists.py"
        existing.write_text("E0\n", encoding="utf-8")
        new_file = tmp_path / "newly.py"

        executor = CodeEditExecutor(tmp_path)
        bad_dir = tmp_path / "boom.py"
        bad_dir.mkdir()

        edits = [
            FileEdit(path=str(new_file), content="N1\n"),
            FileEdit(path=str(existing), content="E1\n"),
            FileEdit(path=str(bad_dir), content="X\n"),
        ]
        with pytest.raises(OSError):
            executor.apply(edits)

        # Newly created file removed on rollback; existing file restored.
        assert not new_file.exists()
        assert existing.read_text(encoding="utf-8") == "E0\n"


class TestApplyPhaseRollback:
    def test_apply_phase_rolls_back_on_failure(self, tmp_path: Path) -> None:
        good = tmp_path / "good.py"
        good.write_text("G0\n", encoding="utf-8")
        bad_dir = tmp_path / "dir.py"
        bad_dir.mkdir()

        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "rollback task")
        state.apply_edits = [
            {"path": str(good), "content": "G1\n"},
            {"path": str(bad_dir), "content": "fails\n"},
        ]
        cfg = runner.config.phases.get("apply")
        phase = ApplyPhase(cfg, BudgetMode.OFF)
        phase_result = phase.run(state)

        # File restored; phase did not report a successful apply.
        assert good.read_text(encoding="utf-8") == "G0\n"
        manifest_path = Path(phase_result.artifacts[0].path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["status"] != "applied"
        assert phase_result.status == GateStatus.FAILED


class TestForbiddenPathEnforcement:
    def test_executor_blocks_forbidden_path_with_zero_mutation(self, tmp_path: Path) -> None:
        """H5: an edit to a forbidden path is blocked before any write."""
        allowed = tmp_path / "src" / "ok.py"
        secret = tmp_path / "secrets" / "token.txt"
        executor = CodeEditExecutor(tmp_path, forbidden_paths=[".env", "secrets/"])

        with pytest.raises(PermissionError):
            executor.apply(
                [
                    FileEdit(path="src/ok.py", content="x = 1\n"),
                    FileEdit(path="secrets/token.txt", content="leak\n"),
                ]
            )

        # Batch check runs before any write: the allowed file is never created.
        assert not allowed.exists()
        assert not secret.exists()

    def test_apply_phase_fails_on_forbidden_edit(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        runner.config.forbidden_paths = [".env"]
        state = runner.create_run("sdd", "leak task")
        state.apply_edits = [{"path": ".env", "content": "SECRET=1\n"}]
        phase = runner._build_phase("apply", BudgetMode.OFF)
        result = phase.run(state)

        assert result.status == GateStatus.FAILED
        assert not (tmp_path / ".env").exists()

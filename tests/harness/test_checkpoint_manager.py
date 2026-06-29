"""PR-002 CHK-02: CheckpointManager records checksums; CheckpointRef in manifest."""

from __future__ import annotations

import hashlib
from pathlib import Path

from opencontext_core.harness.checkpoint import CheckpointManager
from opencontext_core.harness.models import BudgetMode
from opencontext_core.harness.phases import ApplyPhase
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.harness.sessions import build_run_manifest


def test_checkpoint_records_checksums_matching_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    target.write_bytes(b"CONTENT\n")

    manager = CheckpointManager(tmp_path)
    checkpoint = manager.create([target], session_id="sess_1", run_id="run_1")
    assert checkpoint is not None

    model = manager.model(checkpoint, session_id="sess_1", run_id="run_1")
    key = str(target)
    assert key in model.checksums
    assert model.checksums[key] == hashlib.sha256(b"CONTENT\n").hexdigest()
    assert model.snapshot_paths[key]


def test_checkpoint_ref_appears_in_manifest(tmp_path: Path) -> None:
    target = tmp_path / "f.py"
    target.write_text("A\n", encoding="utf-8")

    runner = HarnessRunner(root=tmp_path)
    runner._durable_artifacts = True
    state = runner.create_run("sdd", "checkpoint manifest")
    state.apply_edits = [{"path": str(target), "content": "B\n"}]
    result = ApplyPhase(runner.config.phases.get("apply"), BudgetMode.OFF).run(state)

    run_dir = Path(result.metadata["durable_run_dir"])
    manifest = build_run_manifest(run_dir, session_id=state.session_id, run_id=state.run_id)
    ids = {c.checkpoint_id for c in manifest.checkpoints}
    assert result.metadata["durable_checkpoint_id"] in ids

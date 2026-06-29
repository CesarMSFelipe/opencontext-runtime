"""PR-002 SES-01: session layout, patch artifacts, and the durable kill-switch."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.harness.models import BudgetMode
from opencontext_core.harness.phases import ApplyPhase
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.harness.sessions import build_run_manifest, ensure_layout, next_patch_path


def test_session_layout_is_created(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    expected = tmp_path / ".opencontext" / "sessions" / "sess_1" / "runs" / "run_1"
    assert run_dir == expected
    for sub in ("artifacts", "receipts", "checkpoints", "patches"):
        assert (run_dir / sub).is_dir()


def test_next_patch_path_increments(tmp_path: Path) -> None:
    run_dir = ensure_layout(tmp_path, "sess_1", "run_1")
    p1 = next_patch_path(run_dir)
    p1.write_text("a", encoding="utf-8")
    p2 = next_patch_path(run_dir)
    p2.write_text("b", encoding="utf-8")
    assert p1.name == "patch-001.diff"
    assert p2.name == "patch-002.diff"


def test_patch_persisted_per_mutation_and_referenced(tmp_path: Path) -> None:
    target = tmp_path / "f.py"
    target.write_text("A\n", encoding="utf-8")

    runner = HarnessRunner(root=tmp_path)
    runner._durable_artifacts = True
    state = runner.create_run("sdd", "patch test")
    state.apply_edits = [{"path": str(target), "content": "B\n"}]
    result = ApplyPhase(runner.config.phases.get("apply"), BudgetMode.OFF).run(state)

    run_dir = Path(result.metadata["durable_run_dir"])
    patches = sorted((run_dir / "patches").glob("patch-*.diff"))
    assert len(patches) == 1
    assert patches[0].read_text(encoding="utf-8")  # non-empty unified diff

    manifest = build_run_manifest(run_dir, session_id=state.session_id, run_id=state.run_id)
    assert any(a.kind == "patch" for a in manifest.artifacts)


def test_flag_off_writes_no_session_files(tmp_path: Path) -> None:
    target = tmp_path / "f.py"
    target.write_text("A\n", encoding="utf-8")

    runner = HarnessRunner(root=tmp_path)
    runner._durable_artifacts = False  # exercise the OFF behaviour explicitly, not the default
    state = runner.create_run("sdd", "flag off")
    assert state.durable_artifacts is False
    state.apply_edits = [{"path": str(target), "content": "B\n"}]
    result = ApplyPhase(runner.config.phases.get("apply"), BudgetMode.OFF).run(state)

    # No durable evidence, no sessions tree — PR-001 flat dump only.
    assert "durable_run_dir" not in result.metadata
    assert not (tmp_path / ".opencontext" / "sessions").exists()
    assert (tmp_path / ".opencontext" / "runs" / state.run_id / "apply-manifest.json").exists()

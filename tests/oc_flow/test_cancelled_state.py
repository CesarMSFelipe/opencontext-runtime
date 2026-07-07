"""RUN_STATE_CONTRACT: SIGINT/KeyboardInterrupt yields canonical ``cancelled``.

An interrupted run must (1) report canonical status ``cancelled`` with a
nonzero exit code (the exit_code_for_run mapping: 1) and (2) when the run dir
already exists, persist ``run.json`` with status ``cancelled`` — best-effort,
without corrupting partial artifacts.
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path

import pytest

from opencontext_core.oc_flow.nodes import DeterministicNodeExecutor
from opencontext_core.oc_flow.runner import OCFlowRunner


class _InterruptingExecutor(DeterministicNodeExecutor):
    """Simulates Ctrl-C arriving while the executor is working."""

    def gather_context(self, task: str, seed_paths: Sequence[str], depth: int):
        raise KeyboardInterrupt


# ------------------------------------------------------------------ oc-flow boundary
def test_interrupt_yields_cancelled_result(tmp_path: Path) -> None:
    runner = OCFlowRunner(root=tmp_path, executor=_InterruptingExecutor())

    result = runner.run("fix the bug", session_id="sess-cancel", run_id="run-cancel")

    assert result.status == "cancelled"
    assert result.canonical_status == "cancelled"
    assert result.exit_code == 1


def test_interrupt_persists_cancelled_run_json(tmp_path: Path) -> None:
    runner = OCFlowRunner(root=tmp_path, executor=_InterruptingExecutor())

    result = runner.run("fix the bug", session_id="sess-cancel", run_id="run-cancel")

    run_dir = tmp_path / ".opencontext" / "sessions" / "sess-cancel" / "runs" / "run-cancel"
    assert run_dir.is_dir()
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "cancelled"
    assert manifest["canonical_status"] == "cancelled"
    assert manifest["exit_code"] == result.exit_code == 1
    assert manifest["run_id"] == "run-cancel"


# ------------------------------------------------------------------ harness boundary
def test_harness_interrupt_yields_cancelled(tmp_path: Path, monkeypatch) -> None:
    from opencontext_core.harness.runner import HarnessRunner

    runner = HarnessRunner(root=tmp_path)

    def _interrupt(*_a, **_kw):
        # Simulate the run dir already existing when the interrupt lands.
        state = runner._active_state
        assert state is not None
        run_dir = tmp_path / ".opencontext" / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_resolve_workflow", _interrupt)

    result = runner.run("quick", "fix the bug")

    assert str(getattr(result.status, "value", result.status)) == "cancelled"
    run_dir = tmp_path / ".opencontext" / "runs" / result.run_id
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "cancelled"
    assert manifest["canonical_status"] == "cancelled"
    assert manifest["exit_code"] == 1


def test_harness_interrupt_without_run_dir_skips_persist(tmp_path: Path, monkeypatch) -> None:
    from opencontext_core.harness.runner import HarnessRunner

    runner = HarnessRunner(root=tmp_path)

    def _interrupt(*_a, **_kw):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_resolve_workflow", _interrupt)

    result = runner.run("quick", "fix the bug")

    assert str(getattr(result.status, "value", result.status)) == "cancelled"
    assert not (tmp_path / ".opencontext" / "runs" / result.run_id).exists()


def test_cancelled_maps_to_exit_one() -> None:
    from opencontext_core.models.canonical_status import exit_code_for_run, to_canonical

    assert to_canonical("cancelled").value == "cancelled"
    assert exit_code_for_run("cancelled") == 1


# ---------------------------------------------------------------- SIGINT (smoke)
@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "POSIX SIGINT delivery via Popen.send_signal is unsupported on Windows "
        "(raises ValueError: Unsupported signal: 2). The cancelled-state contract "
        "is covered cross-platform by the in-process KeyboardInterrupt tests above."
    ),
)
def test_sigint_subprocess_smoke(tmp_path: Path) -> None:
    """A real SIGINT during a slow run exits nonzero with run.json cancelled."""
    script = textwrap.dedent(
        """
        import sys
        import time
        from pathlib import Path

        from opencontext_core.oc_flow.nodes import DeterministicNodeExecutor
        from opencontext_core.oc_flow.runner import OCFlowRunner

        class SlowExecutor(DeterministicNodeExecutor):
            def gather_context(self, task, seed_paths, depth):
                print("READY", flush=True)
                time.sleep(90)
                return super().gather_context(task, seed_paths, depth)

        runner = OCFlowRunner(root=Path(sys.argv[1]), executor=SlowExecutor())
        result = runner.run("fix the bug", session_id="sess-sig", run_id="run-sig")
        print(f"STATUS:{result.status}", flush=True)
        sys.exit(result.exit_code)
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline().strip()
        assert line == "READY", f"unexpected first line: {line!r}"
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

    assert proc.returncode != 0, f"stdout={out!r} stderr={err!r}"
    assert "STATUS:cancelled" in out
    run_json = tmp_path / ".opencontext" / "sessions" / "sess-sig" / "runs" / "run-sig" / "run.json"
    assert run_json.is_file()
    assert json.loads(run_json.read_text(encoding="utf-8"))["status"] == "cancelled"


@pytest.fixture(autouse=True)
def _legacy_local_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module asserts the legacy in-repo layout; pin local storage mode."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

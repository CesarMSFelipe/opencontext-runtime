"""Regression tests for the definitive interconnection-review fixes.

Pins the two HIGH-severity broken LIVE loops the review confirmed:
  - #1 CI surface: `opencontext ci-check run` folds in the architecture/quality evaluation.
  - #2 producer handoff: HarnessRunResult carries context_omitted_paths so the memory
    harvester records them as FAILURE linked_nodes (the recent_failure boost source).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from opencontext_core.memory.graph import LocalMemoryStore
from opencontext_core.memory.harvester import MemoryHarvester
from opencontext_core.models.agent_memory import MemoryLayer


@dataclass
class FakeResult:
    run_id: str = "run-omit-1"
    task: str = "add caching to auth"
    status: str = "passed"
    gates: list = field(default_factory=list)
    ledgers: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    context_omitted_paths: list = field(default_factory=list)


def make_store() -> LocalMemoryStore:
    tmpdir = tempfile.mkdtemp()
    return LocalMemoryStore(Path(tmpdir) / "mem.db")


def test_harness_run_result_carries_omitted_paths_field() -> None:
    """The field must exist on HarnessRunResult or the harvester's source-1 is dead."""
    from opencontext_core.harness.models import HarnessRunResult

    result = HarnessRunResult(run_id="r", workflow="w", task="t", status=None)  # type: ignore[arg-type]
    assert hasattr(result, "context_omitted_paths")
    assert result.context_omitted_paths == []


def test_omitted_paths_flow_to_failure_linked_nodes() -> None:
    """#2: omitted paths on the result become FAILURE linked_nodes (boost source)."""
    store = make_store()
    harvester = MemoryHarvester(store)
    result = FakeResult(context_omitted_paths=["src/auth.py:10", "validate_token"])

    records = harvester.harvest(result)

    failure = [r for r in records if r.layer == MemoryLayer.FAILURE]
    assert failure, "omitted paths must produce a FAILURE record for the recent_failure boost"
    linked = failure[0].linked_nodes
    assert "src/auth.py:10" in linked
    # a bare symbol name is normalized to a synthetic file id, never dropped
    assert any("validate_token" in node for node in linked)


def test_no_omitted_paths_writes_no_failure_record() -> None:
    """Guard: a clean run (no omissions) must not spam FAILURE records."""
    store = make_store()
    harvester = MemoryHarvester(store)
    records = harvester.harvest(FakeResult(context_omitted_paths=[]))
    assert not [r for r in records if r.layer == MemoryLayer.FAILURE]


def test_ci_check_run_folds_in_architecture_quality(monkeypatch, tmp_path, capsys) -> None:
    """#1: the `run` report must surface the architecture/quality evaluation.

    Asserts the observable outcome (the rendered report includes the check) rather
    than spying on the lazy import, so it is robust to suite ordering.
    """
    import json

    from opencontext_cli.commands import ci_check_cmd
    from opencontext_core.quality.ci_checks import ARCHITECTURE_CHECK_NAME

    monkeypatch.chdir(tmp_path)
    args = SimpleNamespace(
        ci_check_command="run",
        file=None,
        json=True,
        name=None,
        suite=str(tmp_path / "none.yaml"),
        config=None,
        no_refresh=True,
    )

    ci_check_cmd.handle_ci_check(args)

    report = json.loads(capsys.readouterr().out)
    names = [row.get("check") for row in report.get("results", [])]
    assert ARCHITECTURE_CHECK_NAME in names, (
        f"ci-check run must surface the architecture/quality check; got {names}"
    )

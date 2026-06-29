"""EVT1 / RCPT1 / FLAG1 / INT1 — runner wiring, events, receipt, and flag tests."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.runner import HarnessRunner

_CONFIG_TEMPLATE = """\
project:
  name: t
models:
  default:
    provider: mock
    model: mock-llm
project_index:
  enabled: true
context:
  max_input_tokens: 12000
  reserve_output_tokens: 1500
retrieval:
  strategy: hybrid
  top_k: 20
workflows: {{}}
runtime:
  registry_enabled: {enabled}
"""


def _runner(root: Path, *, registry_enabled: bool) -> HarnessRunner:
    (root / "opencontext.yaml").write_text(
        _CONFIG_TEMPLATE.format(enabled="true" if registry_enabled else "false"),
        encoding="utf-8",
    )
    return HarnessRunner(root=root)


def _ledger_actions(root: Path, run_id: str) -> list[str]:
    data = json.loads((root / ".opencontext" / "runs" / run_id / "events.json").read_text())
    return [e["action"] for e in data["events"]]


def test_flag_on_emits_resolution_events(tmp_path: Path) -> None:
    """EVT1: a flag-on run with 'full' writes alias_resolved + resolved + validated."""
    runner = _runner(tmp_path, registry_enabled=True)
    assert runner._registry_enabled is True
    result = runner.run("full", "demo task")
    actions = _ledger_actions(tmp_path, result.run_id)
    assert "workflow.alias_resolved" in actions
    assert "workflow.resolved" in actions
    assert "workflow.validation.passed" in actions
    # Resolution events precede the first executed phase.
    assert actions.index("workflow.resolved") < actions.index("run_phase")


def test_flag_on_writes_selection_receipt(tmp_path: Path) -> None:
    """RCPT1: a flag-on run records the selection receipt with alias metadata."""
    runner = _runner(tmp_path, registry_enabled=True)
    result = runner.run("standard", "demo task")
    receipt_path = (
        tmp_path / ".opencontext" / "runs" / result.run_id / "workflow-selection.json"
    )
    assert receipt_path.exists()
    receipt = json.loads(receipt_path.read_text())
    assert receipt["requested"] == "standard"
    assert receipt["resolved"] == "sdd"
    assert receipt["profile"] == "standard"
    assert receipt["alias_used"] == "standard"
    assert receipt["schema_version"] == "opencontext.workflow_selection.v1"


def test_flag_off_uses_legacy_path(tmp_path: Path) -> None:
    """FLAG1: a flag-off run reproduces legacy order and invokes no registry code."""
    runner = _runner(tmp_path, registry_enabled=False)
    assert runner._registry_enabled is False
    # No registry is constructed and no workflow events / receipt are produced.
    phase_ids, events = runner._resolve_workflow("full", runner.create_run("full", "t"))
    assert events == []
    assert runner._workflow_registry is None
    assert phase_ids == runner.schedule_phases("full")

    result = runner.run("full", "demo task")
    actions = _ledger_actions(tmp_path, result.run_id)
    assert not any(a.startswith("workflow.") for a in actions)
    assert not (
        tmp_path / ".opencontext" / "runs" / result.run_id / "workflow-selection.json"
    ).exists()


def test_flag_on_off_produce_identical_phase_order(tmp_path: Path) -> None:
    """FLAG1/BAK1: flag-on resolved order equals the flag-off legacy order."""
    (tmp_path / "on").mkdir(exist_ok=True)
    (tmp_path / "off").mkdir(exist_ok=True)
    on = _runner(tmp_path / "on", registry_enabled=True)
    off = _runner(tmp_path / "off", registry_enabled=False)
    for name in ("full", "standard", "quick"):
        on_order, _ = on._resolve_workflow(name, on.create_run(name, "t"))
        off_order, _ = off._resolve_workflow(name, off.create_run(name, "t"))
        assert on_order == off_order


def test_unknown_workflow_falls_back_to_legacy(tmp_path: Path) -> None:
    """task 3.2: a name the registry cannot resolve falls back to the legacy path."""
    runner = _runner(tmp_path, registry_enabled=True)
    # 'full+judgment' is a legacy track with no registry alias -> graceful fallback.
    phase_ids, events = runner._resolve_workflow(
        "full+judgment", runner.create_run("full+judgment", "t")
    )
    assert phase_ids == runner.schedule_phases("full+judgment")
    assert [e.action for e in events] == ["workflow.validation.failed"]


def test_no_generic_workflow_runner_introduced(tmp_path: Path) -> None:
    """INT1: execution stays on HarnessRunner; no generic node-by-node runner."""
    runner = _runner(tmp_path, registry_enabled=True)
    # The resolved order is executed by the existing scheduler/executor loop, which
    # emits run_phase events — there is no separate generic WorkflowRunner attribute.
    assert not hasattr(runner, "workflow_runner")
    result = runner.run("quick", "demo task")
    actions = _ledger_actions(tmp_path, result.run_id)
    assert "run_phase" in actions

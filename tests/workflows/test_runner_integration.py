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
    receipt_path = tmp_path / ".opencontext" / "runs" / result.run_id / "workflow-selection.json"
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


# Every legacy workflow name the legacy HarnessRunner scheduled
# (WORKFLOW_TRACKS + the explore-only/apply-only custom subsets). With
# registry_enabled on, each MUST resolve to the same phase order as the legacy
# scheduler and MUST NOT emit a workflow.validation.failed event (spec VDM-004).
_LEGACY_TRACKS = (
    "full",
    "standard",
    "quick",
    "sdd",
    "explore-only",
    "apply-only",
    "full+judgment",
    "full+gga",
    "full+quality",
)


def test_flag_on_off_produce_identical_phase_order(tmp_path: Path) -> None:
    """FLAG1/BAK1: flag-on resolved order equals the flag-off legacy order."""
    (tmp_path / "on").mkdir(exist_ok=True)
    (tmp_path / "off").mkdir(exist_ok=True)
    on = _runner(tmp_path / "on", registry_enabled=True)
    off = _runner(tmp_path / "off", registry_enabled=False)
    for name in _LEGACY_TRACKS:
        on_order, _ = on._resolve_workflow(name, on.create_run(name, "t"))
        off_order, _ = off._resolve_workflow(name, off.create_run(name, "t"))
        assert on_order == off_order, name


def test_known_legacy_tracks_emit_no_validation_failed(tmp_path: Path) -> None:
    """VDM-004: every known legacy track resolves cleanly under registry-on.

    The spurious ``workflow.validation.failed`` event (which auto-reverted the
    registry flip) is gone for known legacy tracks; the executed-phase ledger is
    unchanged from the legacy path.
    """
    runner = _runner(tmp_path, registry_enabled=True)
    for name in _LEGACY_TRACKS:
        phase_ids, events = runner._resolve_workflow(name, runner.create_run(name, "t"))
        actions = [e.action for e in events]
        assert "workflow.validation.failed" not in actions, name
        # Phase order is byte-identical to the legacy scheduler (parity).
        assert phase_ids == runner.schedule_phases(name), name


def test_unknown_workflow_still_emits_validation_failed(tmp_path: Path) -> None:
    """task 3.2 / VDM-004: validation.failed is reserved for genuinely unknown names.

    A name that is neither a registry alias nor a registered definition falls back
    to the legacy path WITH a ``workflow.validation.failed`` event — the event keeps
    its meaning (a real, unexpected resolution miss) now that every known legacy
    track resolves cleanly.
    """
    runner = _runner(tmp_path, registry_enabled=True)
    phase_ids, events = runner._resolve_workflow(
        "totally-bogus-workflow", runner.create_run("totally-bogus-workflow", "t")
    )
    assert phase_ids == runner.schedule_phases("totally-bogus-workflow")
    assert [e.action for e in events] == ["workflow.validation.failed"]


def _phase_ledger(actions: list[str]) -> list[str]:
    """The executed-phase actions only (drop the registry's workflow.* audit events)."""
    return [a for a in actions if not a.startswith("workflow.")]


def test_event_ledger_phase_parity_under_registry_on(tmp_path: Path) -> None:
    """VDM-004: registry-on legacy runs keep the SAME executed-phase ledger as legacy.

    Mirrors ``tests/harness/test_event_ledger.py`` scenarios with
    ``registry_enabled`` forced True. The spurious ``workflow.validation.failed``
    event is gone; the executed-phase ledger (the ``run_phase``/phase events) is
    byte-identical to the legacy flag-off run. The registry additionally records its
    auditable resolution events (alias_resolved/validation.passed/resolved) by
    design (spec EVT1) — those are not failures and not part of the phase ledger.
    """
    for name in ("explore-only", "apply-only", "sdd"):
        (tmp_path / f"on-{name}").mkdir(exist_ok=True)
        (tmp_path / f"off-{name}").mkdir(exist_ok=True)
        on = _runner(tmp_path / f"on-{name}", registry_enabled=True)
        off = _runner(tmp_path / f"off-{name}", registry_enabled=False)

        on_actions = _ledger_actions(tmp_path / f"on-{name}", on.run(name, "t").run_id)
        off_actions = _ledger_actions(tmp_path / f"off-{name}", off.run(name, "t").run_id)

        # No spurious validation failure under registry-on.
        assert "workflow.validation.failed" not in on_actions, name
        # Executed-phase ledger is identical to the legacy run (parity).
        assert _phase_ledger(on_actions) == _phase_ledger(off_actions) == off_actions, name


def test_no_generic_workflow_runner_introduced(tmp_path: Path) -> None:
    """INT1: execution stays on HarnessRunner; no generic node-by-node runner."""
    runner = _runner(tmp_path, registry_enabled=True)
    # The resolved order is executed by the existing scheduler/executor loop, which
    # emits run_phase events — there is no separate generic WorkflowRunner attribute.
    assert not hasattr(runner, "workflow_runner")
    result = runner.run("quick", "demo task")
    actions = _ledger_actions(tmp_path, result.run_id)
    assert "run_phase" in actions

"""Typed event ledger: one immutable action/observation record per phase."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from opencontext_core.config import default_config_data
from opencontext_core.harness.config import HarnessConfig, PhaseConfig
from opencontext_core.harness.models import BudgetMode, GateStatus, HarnessRunResult
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.models.trace import RunEvent, RuntimeTrace


def _write_config(tmp_path: Path, name: str) -> None:
    cfg = tmp_path / "opencontext.yaml"
    data = default_config_data()
    data["project"]["name"] = name
    cfg.write_text(yaml.safe_dump(data), encoding="utf-8")


class TestRunEventModel:
    def test_event_is_frozen_and_typed(self) -> None:
        event = RunEvent(
            index=0,
            phase="apply",
            action="run_phase",
            inputs_summary="task=demo",
            status="passed",
            observation="applied 1 edit",
        )
        assert event.phase == "apply"
        assert event.action == "run_phase"
        assert event.status == "passed"
        # Immutable: an appended event never changes.
        with pytest.raises(ValidationError):
            event.status = "failed"  # type: ignore[misc]


class TestRunResultLedger:
    def test_one_event_per_executed_phase(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "ledger-explore")
        runner = HarnessRunner(root=tmp_path)
        result = runner.run("explore-only", "ledger task")

        assert isinstance(result, HarnessRunResult)
        # explore-only resolves to a single EXECUTED phase -> exactly one run_phase event.
        # When registry_enabled is on, workflow resolution prepends workflow.* AUDIT
        # events on success (EVT1); the EXECUTED-PHASE ledger is identical to legacy
        # (Phase-4 D), so the invariant is counted over the executed-phase subset.
        executed = [e for e in result.events if e.action == "run_phase"]
        assert len(executed) == 1
        event = executed[0]
        assert event.phase == "explore"
        assert event.action == "run_phase"
        assert event.status
        # Ledger indices are contiguous from 0; the executed event sits after any audits.
        assert [e.index for e in result.events] == list(range(len(result.events)))
        assert event.index == result.events.index(event)

    def test_events_recorded_in_phase_order_with_status(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "ledger-order")
        runner = HarnessRunner(root=tmp_path)
        result = runner.run("sdd", "ordered ledger task")

        # At least the explore phase executes; events are contiguous and ordered.
        assert len(result.events) >= 1
        assert [e.index for e in result.events] == list(range(len(result.events)))
        for e in result.events:
            assert e.phase
            assert e.action
            assert e.status in ("passed", "warning", "failed", "skipped")

    def test_event_ledger_is_persisted_to_run_dir(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "ledger-persist")
        runner = HarnessRunner(root=tmp_path)
        result = runner.run("explore-only", "persisted ledger task")

        events_path = tmp_path / ".opencontext" / "runs" / result.run_id / "events.json"
        assert events_path.exists()
        persisted = json.loads(events_path.read_text(encoding="utf-8"))["events"]
        assert len(persisted) == len(result.events)
        # Exactly one EXECUTED-PHASE (run_phase) event for explore-only; registry audit
        # events (EVT1) may also be persisted but do not change the executed-phase ledger.
        executed = [e for e in persisted if e["action"] == "run_phase"]
        assert len(executed) == 1
        assert executed[0]["phase"] == "explore"
        assert executed[0]["action"] == "run_phase"
        assert "status" in executed[0]
        assert "observation" in executed[0]


class TestBlockedApplyEvent:
    def test_unapproved_apply_records_blocked_event_and_leaves_workspace(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "guarded.py"
        target.write_bytes(b"SAFE = 1\n")

        cfg = HarnessConfig()
        cfg.phases["apply"] = PhaseConfig(
            budget_tokens=12000,
            gates=["approval_required_for_writes"],
        )
        cfg.approval_required_for_writes = True
        runner = HarnessRunner(root=tmp_path, config=cfg)

        result = runner.run(
            "apply-only",
            "needs approval",
            BudgetMode.WARN,
            apply_edits=[{"path": str(target), "content": "HACKED = 1\n"}],
            approved_phases=set(),
        )

        # Workspace untouched — the unapproved apply never wrote.
        assert target.read_bytes() == b"SAFE = 1\n"
        # A typed event records the block as an action/observation.
        apply_events = [e for e in result.events if e.phase == "apply"]
        assert apply_events
        blocked = apply_events[0]
        assert blocked.action == "blocked_pre_gate"
        assert blocked.status == GateStatus.FAILED.value
        assert "approval_required_for_writes" in blocked.observation


class TestRuntimeTraceLedgerField:
    def test_trace_carries_event_ledger_and_roundtrips(self) -> None:
        from datetime import datetime

        from opencontext_core.compat import UTC
        from opencontext_core.models.context import TokenBudget

        trace = RuntimeTrace(
            run_id="r1",
            workflow_name="sdd",
            input="do thing",
            provider="mock",
            model="m",
            selected_context_items=[],
            discarded_context_items=[],
            token_budget=TokenBudget(
                max_input_tokens=100,
                reserve_output_tokens=10,
                available_context_tokens=90,
                sections={},
            ),
            token_estimates={"before": 0, "after": 0},
            compression_strategy="none",
            prompt_sections=[],
            final_answer="ok",
            created_at=datetime.now(tz=UTC),
            event_ledger=[
                RunEvent(index=0, phase="apply", action="run_phase", status="passed"),
            ],
        )
        restored = RuntimeTrace.model_validate_json(trace.model_dump_json())
        assert len(restored.event_ledger) == 1
        assert restored.event_ledger[0].phase == "apply"

    def test_old_trace_json_without_ledger_still_validates(self) -> None:
        # A trace persisted before the ledger field existed must still load.
        from datetime import datetime

        from opencontext_core.compat import UTC
        from opencontext_core.models.context import TokenBudget

        trace = RuntimeTrace(
            run_id="r2",
            workflow_name="sdd",
            input="x",
            provider="mock",
            model="m",
            selected_context_items=[],
            discarded_context_items=[],
            token_budget=TokenBudget(
                max_input_tokens=100,
                reserve_output_tokens=10,
                available_context_tokens=90,
                sections={},
            ),
            token_estimates={"before": 0, "after": 0},
            compression_strategy="none",
            prompt_sections=[],
            final_answer="ok",
            created_at=datetime.now(tz=UTC),
        )
        payload = trace.model_dump(mode="json")
        payload.pop("event_ledger", None)
        restored = RuntimeTrace.model_validate(payload)
        assert restored.event_ledger == []

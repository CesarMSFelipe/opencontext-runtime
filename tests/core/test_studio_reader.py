"""Tests for the read-only Studio data layer (PR-014 — SPEC-STU-014-02..09, STU-CONV).

Every assertion projects from a real ``.opencontext/`` fixture tree written with
the production models/stores, so the reader is exercised against real evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.oc_new.models import ChangeIdentity, NextAction, OcNewRunState, PhaseState
from opencontext_core.oc_new.store import OcNewStore
from opencontext_core.operating_model.receipts import ProviderReceipt, RunReceiptStore
from opencontext_core.runtime.events import make_event
from opencontext_core.runtime.run import RuntimeRun
from opencontext_core.runtime.session import RuntimeSession
from opencontext_core.runtime.session_store import SessionStore
from opencontext_core.studio.reader import StudioReader


def _legacy_run(root: Path, task: str = "add studio mvp", *, blocked: bool = True) -> str:
    store = OcNewStore(root)
    ident = ChangeIdentity.from_task(task)
    state = OcNewRunState(
        identity=ident,
        task=task,
        phases=[
            PhaseState(name="explore", status="passed"),
            PhaseState(name="design", status="running"),
        ],
        current_phase="design",
        blocked_reason="design gate failed: missing ADR" if blocked else None,
        next_action=NextAction(
            kind="request_approval",
            phase="design",
            persona="oc-architect",
            instruction="approve the design",
        ),
    )
    store.save(state)
    return ident.run_id


def _write_run_artifacts(root: Path, run_id: str) -> None:
    rdir = OcNewStore(root).run_dir(run_id)
    (rdir / "receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "change_id": "add-studio-mvp",
                "phase": "design",
                "status": "passed",
                "duration_s": 1.2,
                "artifacts": ["src/foo.py", "docs/adr.md"],
                "risks": ["risk1"],
                "missing_artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    (rdir / "harness-report.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "change_id": "add-studio-mvp",
                "passed": False,
                "failures": ["lint failed"],
                "duration_s": 3.0,
            }
        ),
        encoding="utf-8",
    )
    (rdir / "context-report.json").write_text(
        json.dumps(
            {
                "layers": [
                    {"name": "L1", "token_budget": 1000, "tokens_used": 800, "sources": ["a.py"]}
                ],
                "evidence_refs": ["evidence-1"],
                "omissions": ["dropped large_file.py"],
                "token_budget": 12000,
                "compression_receipts": ["compress-1"],
            }
        ),
        encoding="utf-8",
    )
    (rdir / "memory-report.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "id": "m1",
                        "content": "old belief",
                        "status": "superseded",
                        "superseded_by": "m2",
                    }
                ],
                "conflicts": ["conflict-1"],
            }
        ),
        encoding="utf-8",
    )


def test_list_sessions_newest_first(tmp_path: Path) -> None:
    rid1 = _legacy_run(tmp_path, "first task")
    rid2 = _legacy_run(tmp_path, "second task")
    sessions = StudioReader(tmp_path).list_sessions()
    ids = [s.id for s in sessions]
    assert rid1 in ids and rid2 in ids
    # newest-first ordering by updated_at
    assert sessions == sorted(sessions, key=lambda s: s.updated_at, reverse=True)


def test_session_dashboard_fields(tmp_path: Path) -> None:
    rid = _legacy_run(tmp_path)
    session = StudioReader(tmp_path).session(rid)
    assert session is not None
    assert session.kind == "run"
    assert session.task == "add studio mvp"
    assert session.current_node == "design"
    assert session.status == "blocked"
    assert session.next_action == "approve the design"


def test_session_missing_returns_none(tmp_path: Path) -> None:
    assert StudioReader(tmp_path).session("nope") is None


def test_timeline_persona_skill_and_blocked_gate(tmp_path: Path) -> None:
    rid = _legacy_run(tmp_path)
    timeline = StudioReader(tmp_path).timeline(rid)
    assert timeline.current_node == "design"
    by_name = {n.name: n for n in timeline.nodes}
    assert by_name["explore"].persona == "oc-explorer"
    assert by_name["explore"].skill == "oc-explore"
    design = by_name["design"]
    assert design.persona == "oc-architect"
    assert design.gate_blocked is True
    assert "missing ADR" in (design.gate_reason or "")


def test_context_view_evidence_omissions_budget(tmp_path: Path) -> None:
    rid = _legacy_run(tmp_path)
    _write_run_artifacts(tmp_path, rid)
    ctx = StudioReader(tmp_path).context(rid)
    assert ctx.available is True
    assert ctx.evidence_refs == ["evidence-1"]
    assert ctx.omissions == ["dropped large_file.py"]
    assert ctx.token_budget == 12000
    assert ctx.layers[0].token_budget == 1000


def test_memory_view_flags_superseded(tmp_path: Path) -> None:
    rid = _legacy_run(tmp_path)
    _write_run_artifacts(tmp_path, rid)
    mem = StudioReader(tmp_path).memory(rid)
    assert mem.available is True
    rec = mem.records[0]
    assert rec.superseded is True
    assert rec.superseded_by == "m2"
    assert mem.conflicts == ["conflict-1"]


def test_receipts_view_changed_files(tmp_path: Path) -> None:
    rid = _legacy_run(tmp_path)
    _write_run_artifacts(tmp_path, rid)
    receipts = StudioReader(tmp_path).receipts(rid)
    assert receipts.available is True
    assert "src/foo.py" in receipts.changed_files
    assert receipts.receipts[0].status == "passed"


def test_harness_view(tmp_path: Path) -> None:
    rid = _legacy_run(tmp_path)
    _write_run_artifacts(tmp_path, rid)
    harness = StudioReader(tmp_path).harness(rid)
    assert harness.available is True
    assert harness.passed is False
    assert harness.failures == ["lint failed"]


def test_cost_and_cache_from_provider_receipts(tmp_path: Path) -> None:
    rid = _legacy_run(tmp_path)
    store = RunReceiptStore(tmp_path)
    store.save_provider_receipt(
        ProviderReceipt(
            kind="cost",
            provider="anthropic",
            model="m",
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01,
        )
    )
    store.save_provider_receipt(
        ProviderReceipt(
            kind="provider-call",
            provider="anthropic",
            model="m",
            input_tokens=80,
            output_tokens=10,
            estimated_cost=0.0,
            cache_hit=True,
        )
    )
    reader = StudioReader(tmp_path)
    cost = reader.cost(rid)
    assert cost.available is True
    assert cost.estimated_cost == pytest.approx(0.01)
    assert cost.actual_cost == pytest.approx(0.01)
    assert cost.token_savings == 80
    cache = reader.cache(rid)
    assert cache.hits == 1
    assert cache.misses == 1
    assert cache.hit_rate == pytest.approx(0.5)


def test_capabilities_view_has_remediation(tmp_path: Path) -> None:
    view = StudioReader(tmp_path).capabilities()
    assert view.available is True
    assert view.nodes
    # every unavailable node carries an actionable remediation
    for node in view.nodes:
        if not node.available:
            assert node.remediation


def test_modern_session_event_timelines_and_decisions(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.create_session(
        RuntimeSession(
            session_id="sess-1", root=str(tmp_path), task="modern task", profile="balanced"
        )
    )
    bus = store.event_bus("sess-1")
    for ev in (
        make_event(session_id="sess-1", type="node.started", status="running", node_id="design"),
        make_event(session_id="sess-1", type="context.packed", status="ok"),
        make_event(session_id="sess-1", type="memory.retrieved", status="ok"),
        make_event(session_id="sess-1", type="kg.queried", status="ok"),
    ):
        bus.publish(ev)
    store.create_run(RuntimeRun(run_id="run-1", session_id="sess-1", workflow_id="sdd"))
    run_path = store.run_json("sess-1", "run-1")
    data = json.loads(run_path.read_text(encoding="utf-8"))
    data["decision_log"]["entries"] = [
        {
            "id": "d1",
            "kind": "workflow",
            "chosen": "sdd",
            "rationale": "task is a code change",
            "confidence": 0.9,
            "created_at": "2026-06-29T00:00:00Z",
        }
    ]
    run_path.write_text(json.dumps(data), encoding="utf-8")

    reader = StudioReader(tmp_path)
    ids = [s.id for s in reader.list_sessions()]
    assert "sess-1" in ids

    timelines = reader.timelines("sess-1")
    assert timelines.available is True
    lanes = {lane.lane: lane for lane in timelines.lanes}
    assert lanes["context"].events and lanes["memory"].events and lanes["kg"].events

    decisions = reader.decision_log("sess-1")
    assert decisions.available is True
    assert decisions.decisions[0].rationale == "task is a code change"


def test_config_view_reads_studio_flag(tmp_path: Path) -> None:
    (tmp_path / "opencontext.yaml").write_text(
        "project:\n  name: demo\nprofile: balanced\nstudio:\n  enabled: true\n",
        encoding="utf-8",
    )
    view = StudioReader(tmp_path).config_view()
    assert view.available is True
    assert view.studio_enabled is True
    assert view.profile == "balanced"


def test_unavailable_views_degrade_gracefully(tmp_path: Path) -> None:
    """A run with no artifacts yields available=False, not an exception."""
    rid = _legacy_run(tmp_path, blocked=False)
    reader = StudioReader(tmp_path)
    assert reader.context(rid).available is False
    assert reader.memory(rid).available is False
    assert reader.harness(rid).available is False


# --- N2 read-only surfacing (AVH-019) ----------------------------------------


def _oc_flow_state(root: Path, run_id: str, status: str, *, reason: str) -> None:
    rdir = root / ".opencontext" / "sessions" / f"sess-{run_id}" / "runs" / run_id
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "state.json").write_text(
        json.dumps(
            {
                "schema_version": "opencontext.oc_flow.run_state.v1",
                "run_id": run_id,
                "session_id": f"sess-{run_id}",
                "workflow": "oc-flow",
                "task": "Fix failing test",
                "status": status,
                "completion_reason": reason,
                "mutation_required": True,
            }
        ),
        encoding="utf-8",
    )


def test_task_history_surfaces_blocked_with_reason(tmp_path: Path) -> None:
    _oc_flow_state(tmp_path, "r1", "needs_executor", reason="no executor produced edits")
    _oc_flow_state(tmp_path, "r2", "completed", reason="done")  # must be filtered out
    view = StudioReader(tmp_path).task_history()
    assert view.available is True
    ids = {t.run_id: t for t in view.tasks}
    assert "r1" in ids and "r2" not in ids
    assert ids["r1"].status == "needs_executor"
    assert ids["r1"].reason == "no executor produced edits"
    assert ids["r1"].mutation_required is True
    assert "needs_executor" in view.statuses


def test_task_history_empty_when_no_blocked_runs(tmp_path: Path) -> None:
    assert StudioReader(tmp_path).task_history().available is False


def test_release_gate_panel_from_persisted_verdict(tmp_path: Path) -> None:
    report_path = tmp_path / ".opencontext" / "reports" / "acceptance.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "ready": False,
                "met": 2,
                "not_measured": 3,
                "failed": 0,
                "gates": [
                    {"gate": "first-run", "category": "A", "status": "MET", "detail": "ok"},
                    {
                        "gate": "kg-retrieval",
                        "category": "A",
                        "status": "NOT_MEASURED",
                        "detail": "no fixture",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    view = StudioReader(tmp_path).release_gate()
    assert view.available is True
    assert view.ready is False
    assert view.met == 2 and view.not_measured == 3 and view.failed == 0
    statuses = {g.gate: g.status for g in view.gates}
    assert statuses["first-run"] == "MET"
    assert statuses["kg-retrieval"] == "NOT_MEASURED"


def test_release_gate_panel_unavailable_without_run(tmp_path: Path) -> None:
    assert StudioReader(tmp_path).release_gate().available is False


def test_benchmark_coverage_summary(tmp_path: Path) -> None:
    from opencontext_core.runtime_intelligence import telemetry_layout

    path = tmp_path / telemetry_layout.TELEMETRY_DIR / telemetry_layout.BENCHMARK_HISTORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-06-29T00:00:00Z",
                    "results": [
                        {"suite": "oc-flow", "task_id": "t1", "measured": True, "success": True},
                        {
                            "suite": "kg-retrieval",
                            "task_id": "t2",
                            "measured": False,
                            "success": False,
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    view = StudioReader(tmp_path).benchmark_coverage()
    assert view.available is True
    assert view.total_suites == 2
    assert view.measured_suites == 1
    by_suite = {s.suite: s for s in view.suites}
    assert by_suite["oc-flow"].measured is True and by_suite["oc-flow"].success == 1
    assert by_suite["kg-retrieval"].measured is False


def test_n2_views_carry_no_write_methods(tmp_path: Path) -> None:
    """Read-only invariant: the new N2 views expose no mutate/write/save method."""
    reader = StudioReader(tmp_path)
    for view in (reader.task_history(), reader.release_gate(), reader.benchmark_coverage()):
        for attr in ("save", "write", "delete", "update", "mutate"):
            assert not hasattr(view, attr)

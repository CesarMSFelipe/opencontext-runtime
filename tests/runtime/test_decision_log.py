"""PR-000.4 Decision Log — SelectionKind + DecisionLogEntry + record_selection.

SPEC DL-001 (entry identity, append-only) and DL-002 (six selection kinds,
record the WHY). Extends the PR-000.1 ``DecisionRecorder`` without breaking it.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.runtime.decision_log import (
    DecisionLogEntry,
    DecisionRecorder,
    SelectionKind,
)


def test_selection_kind_has_the_six_selection_kinds() -> None:
    # DL-002: workflow / profile / provider / skill / harness / context.
    members = {k.value for k in SelectionKind}
    assert members == {"workflow", "profile", "provider", "skill", "harness", "context"}


def test_entry_identity_flat_accessors() -> None:
    # DL-001: an entry carries entry_id/run_id/decision_kind/selected/rationale/
    # confidence/created_at, readable without unwrapping the decision.
    recorder = DecisionRecorder()
    entry = recorder.record_selection(
        decision_kind=SelectionKind.workflow,
        selected="oc_flow",
        alternatives=["sdd"],
        rationale="oc_flow is cheaper for this task",
        confidence=0.8,
        run_id="run-1",
    )
    assert isinstance(entry, DecisionLogEntry)
    assert entry.schema_version == "opencontext.decision_log_entry.v1"
    assert entry.entry_id and entry.created_at
    assert entry.run_id == "run-1"
    assert entry.decision_kind == "workflow"
    assert entry.selected == "oc_flow"
    assert "sdd" in entry.alternatives
    assert entry.rationale  # non-empty
    assert entry.confidence == 0.8


def test_workflow_selection_recorded() -> None:
    # DL-002 scenario: workflow oc_flow over sdd.
    recorder = DecisionRecorder()
    entry = recorder.record_selection(
        decision_kind=SelectionKind.workflow,
        selected="oc_flow",
        alternatives=["sdd"],
        rationale="selected oc_flow",
    )
    assert entry.decision_kind == "workflow"
    assert entry.selected == "oc_flow"
    assert "sdd" in entry.alternatives
    assert entry.rationale != ""


def test_append_never_rewrites_priors() -> None:
    # DL-001: N -> N+1, first N unchanged.
    recorder = DecisionRecorder()
    first = recorder.record_selection(decision_kind=SelectionKind.provider, selected="ollama")
    first_id = first.entry_id
    before = len(recorder)
    recorder.record_selection(decision_kind=SelectionKind.profile, selected="fast")
    entries = recorder.entries()
    assert len(entries) == before + 1
    assert entries[0].entry_id == first_id
    assert entries[0].selected == "ollama"


def test_record_selection_persists_jsonl(tmp_path: Path) -> None:
    log_path = tmp_path / "decisions.jsonl"
    recorder = DecisionRecorder(path=log_path)
    recorder.record_selection(decision_kind=SelectionKind.harness, selected="tdd", run_id="r1")
    recorder.record_selection(decision_kind=SelectionKind.context, selected="verified", run_id="r1")
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    reloaded = DecisionLogEntry.model_validate_json(lines[0])
    assert reloaded.selected == "tdd"


def test_ingest_consumes_runtime_decision() -> None:
    from opencontext_core.runtime.decisions import RuntimeDecision

    recorder = DecisionRecorder()
    entry = recorder.ingest(RuntimeDecision(kind="provider", chosen="anthropic", run_id="run-2"))
    assert entry.decision_kind == "provider"
    assert entry.selected == "anthropic"
    assert recorder.log_for_run("run-2")[0].selected == "anthropic"

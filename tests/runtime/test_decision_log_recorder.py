"""DecisionRecorder (Decision API) tests (RB-003/RB-011, doc 59)."""

from __future__ import annotations

from pathlib import Path

from opencontext_core.models.run_envelope import PolicyDecision, RunEnvelope
from opencontext_core.runtime.decision_log import DecisionLogEntry, DecisionRecorder
from opencontext_core.runtime.decisions import RuntimeDecision


def _decision(run_id: str, kind: str, chosen: str) -> RuntimeDecision:
    return RuntimeDecision(kind=kind, chosen=chosen, run_id=run_id)


def test_record_returns_a_decision_log_entry() -> None:
    recorder = DecisionRecorder()
    entry = recorder.record(_decision("run-1", "next_node", "spec"))
    assert isinstance(entry, DecisionLogEntry)
    assert entry.decision.chosen == "spec"
    assert entry.schema_version == "opencontext.decision_log_entry.v1"


def test_append_only_priors_unchanged() -> None:
    recorder = DecisionRecorder()
    first = recorder.record(_decision("run-1", "next_node", "spec"))
    first_id = first.decision.decision_id
    recorder.record(_decision("run-1", "provider", "mock:mock-llm"))
    entries = recorder.entries()
    assert len(entries) == 2
    assert entries[0].decision.decision_id == first_id
    assert entries[0].decision.chosen == "spec"


def test_log_for_run_filters_by_run_id() -> None:
    recorder = DecisionRecorder()
    recorder.record(_decision("run-1", "next_node", "spec"))
    recorder.record(_decision("run-2", "next_node", "design"))
    recorder.record(_decision("run-1", "provider", "mock:mock-llm"))
    run1 = recorder.log_for_run("run-1")
    assert [e.decision.chosen for e in run1] == ["spec", "mock:mock-llm"]
    assert [e.decision.chosen for e in recorder.log_for_run("run-2")] == ["design"]


def test_policy_ref_links_existing_policy_decision_without_duplication() -> None:
    # A policy decision already captured in the RunEnvelope evidence (RB-011).
    policy = PolicyDecision(
        id="pol-1",
        subject="provider:anthropic",
        operation="provider_call",
        decision="denied",
        reason="external providers disabled",
        policy="ProviderPolicy",
    )
    envelope = RunEnvelope(
        run_id="run-1",
        workflow_id="sdd",
        task="demo",
        status="running",
        policy_decisions=[policy],
    )

    recorder = DecisionRecorder()
    entry = recorder.record(_decision("run-1", "provider", "ollama:llama3"), policy_ref=policy.id)
    # The entry references the policy id; it does not re-model the PolicyDecision.
    assert entry.policy_ref == "pol-1"
    assert envelope.policy_decisions[0].id == entry.policy_ref
    assert not hasattr(entry, "policy")  # no parallel policy schema embedded


def test_recorder_appends_jsonl_when_path_given(tmp_path: Path) -> None:
    log_path = tmp_path / "decisions.jsonl"
    recorder = DecisionRecorder(path=log_path)
    recorder.record(_decision("run-1", "next_node", "spec"))
    recorder.record(_decision("run-1", "provider", "mock:mock-llm"))
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    reloaded = DecisionLogEntry.model_validate_json(lines[0])
    assert reloaded.decision.chosen == "spec"

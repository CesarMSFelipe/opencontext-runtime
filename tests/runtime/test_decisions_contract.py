"""Contract tests for the RuntimeDecision / scheduling decision models (RB-002/004)."""

from __future__ import annotations

from opencontext_core.runtime.decisions import (
    DECISION_CONTRACT_VERSION,
    DECISION_EVENT_FAMILY,
    DecisionKind,
    DecisionLog,
    NextNodeDecision,
    RuntimeDecision,
    SchedulingDecision,
    SimulationReport,
    summarize_decision_log,
)


def test_decision_kind_has_exactly_eleven_members() -> None:
    # 8 brain-level + 3 runner-level (C16 / product-closure-r13 + R4 confidence).
    assert len(list(DecisionKind)) == 11
    assert {k.value for k in DecisionKind} == {
        # Brain-level (RuntimeBrain._STRATEGIES entries).
        "next_node",
        "persona",
        "skill_bundle",
        "harnesses",
        "context_strategy",
        "provider",
        "execution_profile",
        "retry_policy",
        # Runner-level: emitted by oc_flow/runner.py, not brain strategies.
        "workflow",
        "memory_promotion",
        # R4: post-run confidence report (runner-level, not a brain strategy).
        "confidence_report",
    }


def test_contract_version_and_event_family() -> None:
    assert DECISION_CONTRACT_VERSION == 1
    assert DECISION_EVENT_FAMILY == "runtime"


def test_schema_versions_match() -> None:
    d = RuntimeDecision(kind="provider", chosen="x")
    assert d.schema_version == "opencontext.runtime_decision.v1"
    assert d.contract_version == 1
    assert NextNodeDecision().schema_version == "opencontext.next_node_decision.v1"
    sd = SchedulingDecision(run_id="r", next_node=NextNodeDecision(), decision=d)
    assert sd.schema_version == "opencontext.scheduling_decision.v1"
    assert SimulationReport().schema_version == "opencontext.simulation_report.v1"


def test_decision_id_uses_dec_ulid_prefix() -> None:
    d = RuntimeDecision(kind="provider", chosen="x")
    assert d.decision_id.startswith("dec_")


def test_selected_and_rationale_alias_chosen_and_reason() -> None:
    d = RuntimeDecision(kind="provider", chosen="anthropic:opus", reason="best for role")
    assert d.selected == "anthropic:opus"
    assert d.rationale == "best for role"


def test_decision_log_appends_in_order_without_rewriting_priors() -> None:
    log = DecisionLog()
    first = log.append(RuntimeDecision(kind="next_node", chosen="spec"))
    first_id = first.decision_id
    log.append(RuntimeDecision(kind="provider", chosen="mock:mock-llm"))
    assert len(log) == 2
    # The first entry is unchanged after the second is appended.
    assert log.entries[0].decision_id == first_id
    assert log.entries[0].chosen == "spec"
    assert [d.kind for d in log.entries] == ["next_node", "provider"]


def test_summarize_decision_log_projects_inspectable_rows() -> None:
    log = DecisionLog()
    log.append(
        RuntimeDecision(
            kind="provider",
            chosen="mock:mock-llm",
            reason="default",
            alternatives=["a", "b"],
        )
    )
    rows = summarize_decision_log(log)
    assert rows[0]["kind"] == "provider"
    assert rows[0]["selected"] == "mock:mock-llm"
    assert rows[0]["alternatives"] == ["a", "b"]
    assert rows[0]["rationale"] == "default"

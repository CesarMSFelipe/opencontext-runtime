"""OC Flow model tests (PR-007, FLOW-4, FLOW-5)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.oc_flow.models import (
    OC_FLOW_CONTRACT_VERSION,
    DiagnosisAttempt,
    Hypothesis,
    InspectionReport,
    TaskContract,
)


def _contract() -> TaskContract:
    return TaskContract(
        scope="fix the failing parser test",
        non_scope=["unrelated modules"],
        acceptance_criteria=["the parser test passes"],
        constraints=["surgical change only"],
        changed_areas=["pkg/parser.py"],
        verification_plan=["run targeted tests"],
        risk_flags=[],
        stop_conditions=["scope grows"],
    )


def test_contract_version_pinned() -> None:
    assert OC_FLOW_CONTRACT_VERSION == 1


def test_task_contract_constructable_with_all_fields() -> None:
    contract = _contract()
    assert contract.scope
    assert contract.acceptance_criteria == ["the parser test passes"]
    assert contract.verification_plan == ["run targeted tests"]
    assert contract.changed_areas == ["pkg/parser.py"]


def test_task_contract_is_frozen() -> None:
    contract = _contract()
    with pytest.raises(ValidationError):
        contract.scope = "something else"  # type: ignore[misc]


def test_task_contract_requires_criteria_and_verification() -> None:
    with pytest.raises(ValidationError):
        TaskContract(scope="x", acceptance_criteria=[], verification_plan=["v"])
    with pytest.raises(ValidationError):
        TaskContract(scope="x", acceptance_criteria=["c"], verification_plan=[])


def _hyps() -> list[Hypothesis]:
    return [
        Hypothesis(statement="a", evidence="e1", confidence=0.6),
        Hypothesis(statement="b", evidence="e2", confidence=0.3),
        Hypothesis(statement="c", evidence="e3", confidence=0.1),
    ]


def test_diagnosis_requires_exactly_three_hypotheses() -> None:
    with pytest.raises(ValidationError):
        DiagnosisAttempt(
            attempt=1,
            reproduction_command="pytest",
            hypotheses=_hyps()[:2],
            selected_hypothesis=0,
            fix_strategy="fix it",
        )
    with pytest.raises(ValidationError):
        DiagnosisAttempt(
            attempt=1,
            reproduction_command="pytest",
            hypotheses=[*_hyps(), Hypothesis(statement="d")],
            selected_hypothesis=0,
            fix_strategy="fix it",
        )


def test_diagnosis_selected_in_range() -> None:
    with pytest.raises(ValidationError):
        DiagnosisAttempt(
            attempt=1,
            reproduction_command="pytest",
            hypotheses=_hyps(),
            selected_hypothesis=3,
            fix_strategy="fix it",
        )


def test_diagnosis_attempt_round_trips() -> None:
    attempt = DiagnosisAttempt(
        attempt=2,
        reproduction_command="python -m pytest -q",
        reproduction_result="AssertionError",
        hypotheses=_hyps(),
        selected_hypothesis=1,
        fix_strategy="adjust the expected value",
    )
    dumped = attempt.model_dump()
    reloaded = DiagnosisAttempt.model_validate(dumped)
    assert reloaded == attempt
    assert reloaded.selected.statement == "b"


def test_diagnosis_attempt_budget_capped() -> None:
    with pytest.raises(ValidationError):
        DiagnosisAttempt(
            attempt=4,  # > MAX_DIAGNOSIS_ATTEMPTS
            reproduction_command="pytest",
            hypotheses=_hyps(),
            selected_hypothesis=0,
            fix_strategy="x",
        )


def test_inspection_report_must_be_zero_llm_tokens() -> None:
    ok = InspectionReport(outcome="passed", llm_tokens=0)
    assert ok.llm_tokens == 0
    with pytest.raises(ValidationError):
        InspectionReport(outcome="passed", llm_tokens=5)

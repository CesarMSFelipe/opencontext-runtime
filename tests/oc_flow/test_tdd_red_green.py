"""TDD RED->GREEN evidence engine (TDD_STRICT_CONTRACT).

Unit tests for the pure evidence/violation logic and the bounded test-run
capture used by OC Flow strict TDD enforcement (AC-012 / AC-013).
"""

from __future__ import annotations

import sys
from pathlib import Path

from opencontext_core.tdd.red_green import (
    CLASSIFICATION_ALREADY_PASSING,
    CLASSIFICATION_ENVIRONMENT_ERROR,
    CLASSIFICATION_NO_TESTS,
    CLASSIFICATION_TEST_FAILURE,
    TDD_NO_TEST_RUNNER,
    TDD_RED_NOT_PROVEN,
    TddEvidence,
    TddRunEvidence,
    capture_test_run,
    classify_test_run,
    evaluate_strict,
    runner_available,
)

#: Output of a genuine executed-and-failed pytest run (proves RED).
_FAILING_OUTPUT = "FAILED tests/test_app.py::test_add - assert 0 == 3\n1 failed in 0.01s"

# ---------------------------------------------------------------------------
# red_proven / green_proven semantics
# ---------------------------------------------------------------------------


def test_red_proven_requires_a_failing_run() -> None:
    red = TddRunEvidence(
        command="pytest -q", exit_code=1, failure_summary=_FAILING_OUTPUT, captured_at="t"
    )
    assert TddEvidence(mode="strict", red=red).red_proven is True


def test_already_passing_test_is_not_red() -> None:
    red = TddRunEvidence(command="pytest -q", exit_code=0, captured_at="t")
    assert TddEvidence(mode="strict", red=red).red_proven is False


def test_missing_red_run_is_not_proven() -> None:
    assert TddEvidence(mode="strict").red_proven is False


def test_green_proven_requires_a_passing_run() -> None:
    green_ok = TddRunEvidence(command="pytest -q", exit_code=0, captured_at="t")
    green_bad = TddRunEvidence(command="pytest -q", exit_code=1, captured_at="t")
    assert TddEvidence(mode="strict", green=green_ok).green_proven is True
    assert TddEvidence(mode="strict", green=green_bad).green_proven is False
    assert TddEvidence(mode="strict").green_proven is False


# ---------------------------------------------------------------------------
# to_json shape (run.json `tdd` block per TDD_STRICT_CONTRACT)
# ---------------------------------------------------------------------------


def test_to_json_carries_contract_fields() -> None:
    red = TddRunEvidence(
        command="pytest tests/test_app.py -q",
        exit_code=1,
        failure_summary="assert 0 == 3",
        captured_at="2026-07-06T00:00:00+00:00",
    )
    green = TddRunEvidence(command="pytest -q", exit_code=0, captured_at="t2")
    payload = TddEvidence(mode="strict", red=red, green=green).to_json()
    assert payload["mode"] == "strict"
    assert payload["red_proven"] is True
    assert payload["green_proven"] is True
    assert payload["red"]["command"] == "pytest tests/test_app.py -q"
    assert payload["red"]["exit_code"] == 1
    assert payload["red"]["failure_summary"] == "assert 0 == 3"
    assert payload["red"]["captured_at"]
    assert payload["green"]["command"] == "pytest -q"
    assert payload["regression"] is None
    assert "violation" not in payload


def test_to_json_includes_violation_when_set() -> None:
    payload = TddEvidence(mode="strict", violation=TDD_NO_TEST_RUNNER).to_json()
    assert payload["violation"] == TDD_NO_TEST_RUNNER
    assert payload["red"] is None
    assert payload["red_proven"] is False


# ---------------------------------------------------------------------------
# evaluate_strict — the pure strict-mode gate
# ---------------------------------------------------------------------------


def test_strict_without_test_runner_is_a_violation() -> None:
    violation = evaluate_strict(mutation_required=True, has_test_command=False, red=None)
    assert violation == TDD_NO_TEST_RUNNER


def test_strict_with_already_green_test_is_a_violation() -> None:
    red = TddRunEvidence(command="pytest -q", exit_code=0, captured_at="t")
    violation = evaluate_strict(mutation_required=True, has_test_command=True, red=red)
    assert violation == TDD_RED_NOT_PROVEN


def test_strict_with_proven_red_is_clean() -> None:
    red = TddRunEvidence(
        command="pytest -q", exit_code=1, failure_summary=_FAILING_OUTPUT, captured_at="t"
    )
    assert evaluate_strict(mutation_required=True, has_test_command=True, red=red) is None


def test_strict_readonly_task_is_clean_without_tests() -> None:
    assert evaluate_strict(mutation_required=False, has_test_command=False, red=None) is None


# ---------------------------------------------------------------------------
# capture_test_run — bounded subprocess evidence
# ---------------------------------------------------------------------------


def test_capture_records_nonzero_exit_and_summary(tmp_path: Path) -> None:
    evidence = capture_test_run(
        [sys.executable, "-c", "print('boom detail'); raise SystemExit(3)"], tmp_path
    )
    assert evidence.exit_code == 3
    assert "boom detail" in evidence.failure_summary
    assert evidence.captured_at
    assert sys.executable in evidence.command


def test_capture_records_clean_exit_with_empty_summary(tmp_path: Path) -> None:
    evidence = capture_test_run([sys.executable, "-c", "print('ok')"], tmp_path)
    assert evidence.exit_code == 0
    assert evidence.failure_summary == ""


def test_capture_survives_a_missing_binary(tmp_path: Path) -> None:
    evidence = capture_test_run(["definitely-not-a-real-binary-xyz"], tmp_path)
    assert evidence.exit_code == -1
    assert evidence.failure_summary
    assert evidence.classification == CLASSIFICATION_ENVIRONMENT_ERROR


# ---------------------------------------------------------------------------
# classification — environment/usage errors are never RED (TDD_STRICT_CONTRACT)
# ---------------------------------------------------------------------------


def _fake_run(tmp_path: Path, *, out: str, code: int) -> TddRunEvidence:
    """Capture evidence from a fake test runner emitting *out* and exiting *code*."""
    script = f"import sys; sys.stderr.write({out!r}); sys.exit({code})"
    return capture_test_run([sys.executable, "-c", script], tmp_path)


def test_missing_pytest_is_environment_error_not_red(tmp_path: Path) -> None:
    """`python -m pytest` without pytest exits 1 — that is NOT a proven RED."""
    evidence = _fake_run(tmp_path, out="/usr/bin/python3: No module named pytest\n", code=1)
    assert evidence.exit_code == 1
    assert evidence.classification == CLASSIFICATION_ENVIRONMENT_ERROR
    assert TddEvidence(mode="strict", red=evidence).red_proven is False


def test_environment_error_red_routes_to_no_test_runner(tmp_path: Path) -> None:
    evidence = _fake_run(tmp_path, out="/usr/bin/python3: No module named pytest\n", code=1)
    violation = evaluate_strict(mutation_required=True, has_test_command=True, red=evidence)
    assert violation == TDD_NO_TEST_RUNNER


def test_no_tests_collected_is_not_red(tmp_path: Path) -> None:
    """Pytest exit 5 (no tests collected) must not prove RED; strict mode blocks."""
    evidence = _fake_run(tmp_path, out="no tests ran in 0.01s\n", code=5)
    assert evidence.classification == CLASSIFICATION_NO_TESTS
    assert TddEvidence(mode="strict", red=evidence).red_proven is False
    violation = evaluate_strict(mutation_required=True, has_test_command=True, red=evidence)
    assert violation == TDD_NO_TEST_RUNNER


def test_usage_error_exit_codes_are_environment_errors(tmp_path: Path) -> None:
    """Pytest exit codes 2/3/4 (interrupted/internal/usage) are invalid RED."""
    for code in (2, 3, 4):
        evidence = _fake_run(tmp_path, out="ERROR: usage: pytest [options]\n", code=code)
        assert evidence.classification == CLASSIFICATION_ENVIRONMENT_ERROR, code
        assert TddEvidence(mode="strict", red=evidence).red_proven is False


def test_genuine_failure_is_classified_and_proven(tmp_path: Path) -> None:
    evidence = _fake_run(tmp_path, out=_FAILING_OUTPUT + "\n", code=1)
    assert evidence.classification == CLASSIFICATION_TEST_FAILURE
    assert TddEvidence(mode="strict", red=evidence).red_proven is True
    assert evaluate_strict(mutation_required=True, has_test_command=True, red=evidence) is None


def test_exit_one_without_failure_evidence_is_not_red(tmp_path: Path) -> None:
    evidence = _fake_run(tmp_path, out="something went wrong\n", code=1)
    assert evidence.classification == CLASSIFICATION_ENVIRONMENT_ERROR
    assert TddEvidence(mode="strict", red=evidence).red_proven is False


def test_classify_already_passing() -> None:
    assert classify_test_run(0, "3 passed in 0.01s") == CLASSIFICATION_ALREADY_PASSING


def test_to_json_carries_classification(tmp_path: Path) -> None:
    """The run.json tdd block records the RED classification (additive field)."""
    red = _fake_run(tmp_path, out="/usr/bin/python3: No module named pytest\n", code=1)
    payload = TddEvidence(mode="strict", red=red).to_json()
    assert payload["red"]["classification"] == CLASSIFICATION_ENVIRONMENT_ERROR
    assert payload["red_proven"] is False


# ---------------------------------------------------------------------------
# runner_available — preflight before counting RED
# ---------------------------------------------------------------------------


def test_runner_available_true_for_installed_module() -> None:
    assert runner_available([sys.executable, "-m", "pytest", "-q"]) is True


def test_runner_available_false_for_missing_module() -> None:
    assert runner_available([sys.executable, "-m", "definitely_missing_runner_xyz"]) is False


def test_runner_available_false_for_missing_binary() -> None:
    assert runner_available(["definitely-not-a-real-binary-xyz", "-q"]) is False


def test_runner_available_false_for_empty_command() -> None:
    assert runner_available([]) is False

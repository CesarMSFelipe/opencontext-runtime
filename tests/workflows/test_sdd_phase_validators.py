"""SDD phase contract validators block junk executor output."""

from __future__ import annotations

from types import SimpleNamespace

from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.sdd.validators import validate_phase


class _JunkDelegate:
    def delegate(self, phase: str, context: dict[str, object]) -> object:
        return SimpleNamespace(status="success", output="ok")


class _ValidDelegate:
    def delegate(self, phase: str, context: dict[str, object]) -> object:
        outputs = {
            "spec": "### Requirement: X\nMUST do X.\nGIVEN input\nWHEN run\nTHEN output\n",
            "design": "Technical approach\nAffected modules\nData flow\nRisks\nRollback plan\n",
            "tasks": '{"tasks":[{"id":"1","description":"edit file","file_paths":["x.py"]}]}',
        }
        return SimpleNamespace(status="success", output=outputs.get(phase, "ok"))


def test_spec_validator_rejects_ok() -> None:
    result = validate_phase("spec", "ok")
    assert result.passed is False
    assert result.reason == "phase output failed contract validation"


def test_valid_spec_validator_accepts_requirements_and_scenarios() -> None:
    result = validate_phase(
        "spec",
        "### Requirement: X\nMUST do X.\nGIVEN input\nWHEN run\nTHEN output\n",
    )
    assert result.passed is True


def test_design_and_tasks_validators_accept_contract_outputs() -> None:
    assert validate_phase(
        "design",
        "Technical approach\\nAffected modules\\nData flow\\nRisks\\nRollback plan",
    ).passed
    assert validate_phase(
        "tasks",
        '{"tasks":[{"id":"1","description":"edit file","file_paths":["x.py"]}]}',
    ).passed


def test_tasks_validator_rejects_missing_file_mapping() -> None:
    """Tasks without file/verification mapping must fail (task 3.6)."""
    # Missing file_paths/files/verification/acceptance_criteria
    result = validate_phase(
        "tasks",
        '{"tasks":[{"id":"1","description":"do something"}]}',
    )
    assert result.passed is False
    assert result.reason == "phase output failed contract validation"


def test_tasks_validator_accepts_verification_mapping() -> None:
    """Tasks with verification field pass even without file_paths."""
    result = validate_phase(
        "tasks",
        '{"tasks":[{"id":"1","description":"do something","verification":"pytest passes"}]}',
    )
    assert result.passed is True


def test_explore_validator_rejects_ok() -> None:
    result = validate_phase("explore", "ok")
    assert result.passed is False


def test_explore_validator_accepts_context_summary() -> None:
    result = validate_phase(
        "explore", "Context summary: project has files and symbols. unknowns: none."
    )
    assert result.passed is True


def test_proposal_validator_rejects_missing_scope() -> None:
    """proposal without scope must fail (task 3.3)."""
    result = validate_phase("proposal", "intent: add feature. risks: high")
    assert result.passed is False


def test_proposal_validator_accepts_full_fields() -> None:
    result = validate_phase("proposal", "intent: add feature. scope: x.py. risks: high")
    assert result.passed is True


def test_apply_validator_rejects_empty_output() -> None:
    result = validate_phase("apply", "")
    assert result.passed is False


def test_apply_validator_accepts_planned_only_status() -> None:
    result = validate_phase("apply", "planned_only: no executor wired")
    assert result.passed is True


def test_verify_validator_rejects_ok() -> None:
    result = validate_phase("verify", "ok")
    assert result.passed is False


def test_verify_validator_accepts_required_fields() -> None:
    result = validate_phase("verify", "command: pytest. outcome: passed")
    assert result.passed is True


def test_review_validator_accepts_required_fields() -> None:
    result = validate_phase("review", "finding: none. severity: low")
    assert result.passed is True


def test_archive_validator_accepts_required_fields() -> None:
    result = validate_phase("archive", "status: done. artifact: archive-report.json")
    assert result.passed is True


def test_sdd_harness_surfaces_junk_spec_output_as_warning(tmp_path, monkeypatch) -> None:
    """Junk spec output raises a phase_contract WARNING (not FAILED).

    Hard blocking only occurs in sdd_strict mode via contract_blocked in the runner.
    This test verifies the warning is surfaced; separate strict-mode tests cover blocking.
    """
    monkeypatch.setattr(HarnessRunner, "_build_executor", lambda self: _JunkDelegate())

    result = HarnessRunner(root=tmp_path).run("standard", "add feature")

    assert any(
        gate.id == "phase_contract"
        and gate.phase == "spec"
        and gate.status.value == "warning"
        and gate.message == "phase output failed contract validation"
        for gate in result.gates
    )


def test_sdd_harness_accepts_valid_phase_outputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(HarnessRunner, "_build_executor", lambda self: _ValidDelegate())

    result = HarnessRunner(root=tmp_path).run("standard", "add feature")

    contract_gates = [g for g in result.gates if g.id == "phase_contract"]
    assert contract_gates
    assert all(g.status.value in {"passed", "skipped"} for g in contract_gates)

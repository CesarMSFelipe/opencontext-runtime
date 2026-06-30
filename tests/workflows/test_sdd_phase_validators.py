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


def test_sdd_harness_blocks_junk_spec_output(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(HarnessRunner, "_build_executor", lambda self: _JunkDelegate())

    result = HarnessRunner(root=tmp_path).run("standard", "add feature")

    assert result.status.value == "failed"
    assert any(
        gate.id == "phase_contract"
        and gate.phase == "spec"
        and gate.status.value == "failed"
        and gate.message == "phase output failed contract validation"
        for gate in result.gates
    )


def test_sdd_harness_accepts_valid_phase_outputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(HarnessRunner, "_build_executor", lambda self: _ValidDelegate())

    result = HarnessRunner(root=tmp_path).run("standard", "add feature")

    contract_gates = [g for g in result.gates if g.id == "phase_contract"]
    assert contract_gates
    assert all(g.status.value in {"passed", "skipped"} for g in contract_gates)

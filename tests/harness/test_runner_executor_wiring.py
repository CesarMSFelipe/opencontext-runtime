"""HarnessRunner wires a live executor to the run state from the gateway.

The planning phases (spec/design/tasks) read an executor/delegation layer off
``state.delegate`` (see ``run_phase_executor``). Previously the runner never
constructed or attached one, so those phases always reported executor-absent.

These tests pin the wiring contract:

  - When a real (non-mock) LLM gateway is available, ``HarnessRunner`` builds a
    delegate from it and attaches it to the run state. A spec/design/tasks phase
    then runs it: ``status == PASSED`` and ``metadata["executor"] == "real"``,
    with the gateway's content landing in the artifact.
  - When only the default mock/local provider is configured (no real LLM), the
    runner attaches NO delegate. The phases keep their honest
    planned/executor-absent behavior — never faked success.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.harness.config import PhaseConfig
from opencontext_core.harness.models import BudgetMode, GateStatus
from opencontext_core.harness.phases import (
    DesignPhase,
    SpecPhase,
    TasksPhase,
)
from opencontext_core.harness.runner import HarnessRunner
from opencontext_core.models.llm import LLMRequest, LLMResponse


class _FakeGateway:
    """A real (non-mock) gateway: returns phase-tagged content per call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request.prompt)
        return LLMResponse(
            content=f"REAL EXECUTOR CONTENT :: {request.prompt[:40]}",
            provider=request.provider,
            model=request.model,
            input_tokens=1,
            output_tokens=1,
        )


def _seed_upstream(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "proposal.json").write_text(
        json.dumps({"task": "wire executor", "approach": {"method": "incremental"}}),
        encoding="utf-8",
    )
    (run_dir / "spec.md").write_text(
        "# Spec\n\n### Requirement: Wire\nMUST wire the executor.\n",
        encoding="utf-8",
    )
    (run_dir / "design.md").write_text(
        "# Design\n\n## Files to Create/Modify\n\n- src/wire.py\n",
        encoding="utf-8",
    )


def _cfg(runner: HarnessRunner, phase: str) -> PhaseConfig:
    cfg = runner.config.phases.get(phase)
    assert cfg is not None
    return cfg


class TestRunnerAttachesExecutorFromGateway:
    def test_real_gateway_yields_real_executor_on_state(self, tmp_path: Path) -> None:
        gateway = _FakeGateway()
        runner = HarnessRunner(root=tmp_path, llm_gateway=gateway)
        state = runner.create_run("sdd", "wire executor")
        state.root = tmp_path
        _seed_upstream(tmp_path / ".opencontext" / "runs" / state.run_id)

        # The runner must have attached a callable delegation layer.
        delegate = getattr(state, "delegate", None)
        assert delegate is not None
        assert callable(getattr(delegate, "delegate", None))

        result = SpecPhase(_cfg(runner, "spec"), BudgetMode.OFF).run(state)

        assert result.status == GateStatus.PASSED
        assert result.metadata.get("executor") == "real"
        assert gateway.calls, "the real gateway must have been invoked"
        body = Path(result.artifacts[0].path).read_text(encoding="utf-8")
        assert "REAL EXECUTOR CONTENT" in body

    def test_design_and_tasks_run_real_executor(self, tmp_path: Path) -> None:
        gateway = _FakeGateway()
        runner = HarnessRunner(root=tmp_path, llm_gateway=gateway)
        state = runner.create_run("sdd", "wire executor")
        state.root = tmp_path
        _seed_upstream(tmp_path / ".opencontext" / "runs" / state.run_id)

        design = DesignPhase(_cfg(runner, "design"), BudgetMode.OFF).run(state)
        tasks = TasksPhase(_cfg(runner, "tasks"), BudgetMode.OFF).run(state)

        assert design.status == GateStatus.PASSED
        assert design.metadata.get("executor") == "real"
        assert tasks.status == GateStatus.PASSED
        assert tasks.metadata.get("executor") == "real"


class TestRunnerNoExecutorWhenMock:
    def test_default_mock_config_attaches_no_delegate(self, tmp_path: Path) -> None:
        # No gateway injected and no opencontext.yaml → mock/local default.
        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "wire executor")
        assert getattr(state, "delegate", None) is None

    def test_planning_phase_honest_when_mock(self, tmp_path: Path) -> None:
        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "wire executor")
        state.root = tmp_path
        _seed_upstream(tmp_path / ".opencontext" / "runs" / state.run_id)

        result = SpecPhase(_cfg(runner, "spec"), BudgetMode.OFF).run(state)

        assert result.status != GateStatus.PASSED
        assert result.metadata.get("executor") == "absent"
        manifest = json.loads(Path(result.metadata["manifest_path"]).read_text(encoding="utf-8"))
        assert manifest["status"] == "planned"

    def test_explicit_mock_provider_yaml_attaches_no_delegate(self, tmp_path: Path) -> None:
        # Even with a real config file present, a mock provider stays honest.
        (tmp_path / "opencontext.yaml").write_text(
            "project:\n  name: t\nmodels:\n  default:\n    provider: mock\n    model: mock-llm\n",
            encoding="utf-8",
        )
        runner = HarnessRunner(root=tmp_path)
        state = runner.create_run("sdd", "wire executor")
        assert getattr(state, "delegate", None) is None


class _EditGateway:
    """A real gateway that returns a JSON file-edit array (apply codegen)."""

    def __init__(self, edits_json: str) -> None:
        self._json = edits_json
        self.calls: list[str] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request.prompt)
        return LLMResponse(
            content=self._json, provider=request.provider, model=request.model,
            input_tokens=1, output_tokens=1,
        )


class TestApplyCodegen:
    def test_parse_file_edits_tolerates_fences_and_prose(self) -> None:
        from opencontext_core.agents.executor import parse_file_edits

        text = (
            "Here are the edits:\n```json\n"
            '[{"path": "a.py", "content": "x = 1\\n"}, {"bad": 1}]\n```\n'
        )
        edits = parse_file_edits(text)
        assert edits == [{"path": "a.py", "content": "x = 1\n"}]  # bad item dropped
        assert parse_file_edits("no json here") == []

    def test_apply_writes_edits_generated_by_the_model(self, tmp_path: Path) -> None:
        """C4: a real executor now produces file edits so apply writes source."""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        edits = json.dumps([{"path": "src/new.py", "content": "x = 1\n"}])
        runner = HarnessRunner(root=tmp_path, llm_gateway=_EditGateway(edits))

        result = runner.run("sdd", "add a module", BudgetMode.OFF)

        assert (tmp_path / "src" / "new.py").read_text(encoding="utf-8") == "x = 1\n"
        manifest = json.loads(
            (tmp_path / ".opencontext" / "runs" / result.run_id / "apply-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["status"] == "applied"
        assert any(c["path"].endswith("new.py") for c in manifest["changes"])

    def test_apply_stays_planned_when_model_returns_no_edits(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        runner = HarnessRunner(root=tmp_path, llm_gateway=_EditGateway("no edits here"))

        result = runner.run("sdd", "add a module", BudgetMode.OFF)

        manifest = json.loads(
            (tmp_path / ".opencontext" / "runs" / result.run_id / "apply-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["status"] == "planned"


class TestRunnerFullRunWithExecutor:
    def test_full_run_records_real_executor_for_planning_phases(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        gateway = _FakeGateway()
        runner = HarnessRunner(root=tmp_path, llm_gateway=gateway)
        result = runner.run("sdd", "wire executor end to end", BudgetMode.OFF)

        run_dir = tmp_path / ".opencontext" / "runs" / result.run_id
        # Each planning phase persisted a manifest marked completed by a real executor.
        for phase in ("spec", "design", "tasks"):
            manifest_path = run_dir / f"{phase}-manifest.json"
            assert manifest_path.exists(), f"missing {phase} manifest"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            assert manifest["executor"] == "real"
            assert manifest["status"] == "completed"

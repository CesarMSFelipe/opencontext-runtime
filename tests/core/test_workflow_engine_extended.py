"""Tests for extended workflow engine features.

Covers parallel steps, if/switch control flow, fan-out/fan-in,
and pause/resume.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from opencontext_core.models.workflow import WorkflowRunState
from opencontext_core.workflow.engine import WorkflowEngine
from opencontext_core.workflow.steps import WorkflowServices

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_step_registry() -> dict[str, Any]:
    """Create a simple step registry for testing."""

    def step_a(state: Any, services: Any) -> str:
        state.metadata.setdefault("steps", []).append("a")
        return "step a done"

    def step_b(state: Any, services: Any) -> str:
        state.metadata.setdefault("steps", []).append("b")
        return "step b done"

    def step_c(state: Any, services: Any) -> str:
        state.metadata.setdefault("steps", []).append("c")
        return "step c done"

    def step_fail(state: Any, services: Any) -> str:
        msg = "step fail"
        raise RuntimeError(msg)

    return {
        "step.a": step_a,
        "step.b": step_b,
        "step.c": step_c,
        "step.fail": step_fail,
    }


def _make_config(workflow_name: str, steps: list[Any]) -> Any:
    """Create a minimal config-like object with the given workflow."""
    from types import SimpleNamespace

    return SimpleNamespace(
        workflows={workflow_name: SimpleNamespace(steps=steps)},
        models=SimpleNamespace(default=SimpleNamespace(provider="mock", model="mock")),
        project_index=SimpleNamespace(enabled=False, root=".", profile="generic", ignore=[]),
        context=SimpleNamespace(
            max_input_tokens=1000,
            reserve_output_tokens=500,
            sections=SimpleNamespace(system=100, instructions=100, tool_schemas=100),
        ),
        workflow=SimpleNamespace(max_iterations=100),
        security=SimpleNamespace(mode="private_project"),
        embedding=SimpleNamespace(enabled=False),
        cache=SimpleNamespace(ttl_seconds=3600, max_entries=100),
    )


def _make_services() -> WorkflowServices:
    from unittest.mock import MagicMock

    return MagicMock(spec=WorkflowServices)


# ── Structured Step Config Tests ─────────────────────────────────────────────


def test_steps_accept_string_and_dict_mixed() -> None:
    """WorkflowConfig should accept a mix of strings and structured dicts."""
    from opencontext_core.config import WorkflowStepDef

    # All string steps (backward compat)
    all_strings = [WorkflowStepDef(step="step.a"), WorkflowStepDef(step="step.b")]
    assert len(all_strings) == 2

    # Structured step
    parallel = WorkflowStepDef(type="parallel", steps=["step.a", "step.b"])
    assert parallel.type == "parallel"

    # Mixed
    mixed = [
        WorkflowStepDef(step="step.a"),
        WorkflowStepDef(type="parallel", steps=["step.b", "step.c"]),
    ]
    assert mixed[0].step == "step.a"
    assert mixed[1].type == "parallel"


# ── Basic execution tests (backward compat) ──────────────────────────────────


def test_simple_step_execution() -> None:
    """Plain string steps should still work."""
    config = _make_config("test", ["step.a", "step.b"])
    state = WorkflowRunState(run_id="r1", workflow_name="test", user_request="test")
    engine = WorkflowEngine(config, _make_services(), registry=_make_step_registry())
    result = engine.run_workflow(state, config.workflows["test"])

    assert result.metadata["steps"] == ["a", "b"]


# ── Parallel step execution ──────────────────────────────────────────────────


def test_parallel_steps_execute_all() -> None:
    """Parallel steps should all execute."""
    config = _make_config(
        "test",
        [
            "step.a",
            {"type": "parallel", "steps": ["step.b", "step.c"]},
        ],
    )
    state = WorkflowRunState(run_id="r1", workflow_name="test", user_request="test")
    engine = WorkflowEngine(config, _make_services(), registry=_make_step_registry())
    result = engine.run_workflow(state, config.workflows["test"])

    assert "a" in result.metadata["steps"]
    assert "b" in result.metadata["steps"]
    assert "c" in result.metadata["steps"]


def test_parallel_steps_raises_on_failure() -> None:
    """If one parallel step fails, the error should propagate."""
    config = _make_config(
        "test",
        [
            {"type": "parallel", "steps": ["step.a", "step.fail"]},
        ],
    )
    state = WorkflowRunState(run_id="r1", workflow_name="test", user_request="test")
    engine = WorkflowEngine(config, _make_services(), registry=_make_step_registry())

    with pytest.raises(RuntimeError, match="step fail"):
        engine.run_workflow(state, config.workflows["test"])


# ── If / Else control flow ───────────────────────────────────────────────────


def test_if_condition_true_runs_then_branch() -> None:
    """When condition evaluates to True, the 'then' branch runs."""

    def _check_condition(state: Any) -> bool:
        return True

    config = _make_config(
        "test",
        [
            {
                "type": "if",
                "condition": _check_condition,
                "then": ["step.a", "step.b"],
                "else": ["step.c"],
            },
        ],
    )
    state = WorkflowRunState(run_id="r1", workflow_name="test", user_request="test")
    engine = WorkflowEngine(config, _make_services(), registry=_make_step_registry())
    result = engine.run_workflow(state, config.workflows["test"])

    assert result.metadata["steps"] == ["a", "b"]


def test_if_condition_false_runs_else_branch() -> None:
    """When condition evaluates to False, the 'else' branch runs."""

    def _check_condition(state: Any) -> bool:
        return False

    config = _make_config(
        "test",
        [
            {
                "type": "if",
                "condition": _check_condition,
                "then": ["step.a"],
                "else": ["step.b", "step.c"],
            },
        ],
    )
    state = WorkflowRunState(run_id="r1", workflow_name="test", user_request="test")
    engine = WorkflowEngine(config, _make_services(), registry=_make_step_registry())
    result = engine.run_workflow(state, config.workflows["test"])

    assert result.metadata["steps"] == ["b", "c"]


def test_if_without_else_is_optional() -> None:
    """If no else branch, nothing runs when condition is False."""

    def _check_condition(state: Any) -> bool:
        return False

    config = _make_config(
        "test",
        [
            {"type": "if", "condition": _check_condition, "then": ["step.a"]},
            "step.b",
        ],
    )
    state = WorkflowRunState(run_id="r1", workflow_name="test", user_request="test")
    engine = WorkflowEngine(config, _make_services(), registry=_make_step_registry())
    result = engine.run_workflow(state, config.workflows["test"])

    assert result.metadata["steps"] == ["b"]


# ── Pause / Resume ───────────────────────────────────────────────────────────


def test_save_and_load_state(tmp_path: Path) -> None:
    """WorkflowRunState can be serialized and restored."""
    state = WorkflowRunState(
        run_id="r1",
        workflow_name="test",
        user_request="test request",
        metadata={"steps": ["a", "b"], "counter": 42},
    )
    path = tmp_path / "state.json"
    state.save(path)

    loaded = WorkflowRunState.load(path)
    assert loaded.run_id == "r1"
    assert loaded.workflow_name == "test"
    assert loaded.user_request == "test request"
    assert loaded.metadata["steps"] == ["a", "b"]
    assert loaded.metadata["counter"] == 42


def test_resume_from_saved_state(tmp_path: Path) -> None:
    """Engine should skip completed steps on resume."""
    config = _make_config(
        "test",
        ["step.a", "step.b", "step.c"],
    )
    path = tmp_path / "state.json"

    # Run until step index 1 (completed step.a)
    state = WorkflowRunState(
        run_id="r-resume",
        workflow_name="test",
        user_request="test",
        metadata={"step_index": 1, "steps": []},
    )
    state.save(path)

    engine = WorkflowEngine(config, _make_services(), registry=_make_step_registry())

    # Resume: should start from step index 1 (step.b)
    resumed = WorkflowRunState.load(path)
    result = engine.run_workflow(resumed, config.workflows["test"])

    # Should have executed step.b and step.c (NOT step.a again)
    assert result.metadata["steps"] == ["b", "c"]


def test_resume_at_end_is_noop(tmp_path: Path) -> None:
    """Resuming when all steps complete should be a no-op."""
    config = _make_config("test", ["step.a"])
    path = tmp_path / "state.json"

    state = WorkflowRunState(
        run_id="r-done",
        workflow_name="test",
        user_request="test",
        metadata={"step_index": 1, "steps": ["a"]},
    )
    state.save(path)

    engine = WorkflowEngine(config, _make_services(), registry=_make_step_registry())
    resumed = WorkflowRunState.load(path)
    result = engine.run_workflow(resumed, config.workflows["test"])

    assert result.metadata["steps"] == ["a"]  # unchanged


# ── Fan-out / Fan-in ─────────────────────────────────────────────────────────


def test_fan_out_runs_step_with_multiple_inputs() -> None:
    """Fan-out executes the same step with each input."""

    results: list[str] = []

    def fan_step(state: Any, services: Any) -> str:
        inp = state.metadata.get("current_input", "?")
        results.append(inp)
        state.metadata.setdefault("steps", []).append(f"fan-{inp}")
        return f"done {inp}"

    config = _make_config(
        "test",
        [
            {
                "type": "fan-out",
                "step": "step.fan",
                "inputs": ["x", "y", "z"],
            },
        ],
    )
    registry = {"step.fan": fan_step}
    state = WorkflowRunState(run_id="r1", workflow_name="test", user_request="test")
    engine = WorkflowEngine(config, _make_services(), registry=registry)
    engine.run_workflow(state, config.workflows["test"])

    assert results == ["x", "y", "z"]
    assert state.metadata["steps"] == ["fan-x", "fan-y", "fan-z"]

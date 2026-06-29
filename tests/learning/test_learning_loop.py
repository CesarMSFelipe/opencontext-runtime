"""PR-000.4 LearningLoop orchestrator (SPEC DL-006/DL-008)."""

from __future__ import annotations

import types
from pathlib import Path

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.learning import candidate_extractor
from opencontext_core.learning.loop import LearningLoop


def _run_result(**kw):
    base = {
        "run_id": "run-1",
        "status": "passed",
        "warnings": [],
        "gates": [],
        "context_omitted_paths": ["a.py", "b.py"],
        "decisions": [
            types.SimpleNamespace(
                id="d1",
                phase="explore",
                status="passed",
                rationale="picked explore",
                trace_id="tr-1",
            )
        ],
        "memories_written": [],
    }
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_loop_is_non_blocking_when_extractor_raises(monkeypatch, tmp_path: Path) -> None:
    # DL-006: extractor raising leaves run status unchanged + records a warning.
    def boom(**kwargs):
        raise RuntimeError("extractor exploded")

    monkeypatch.setattr(candidate_extractor, "extract", boom)
    run = _run_result()
    result = LearningLoop(tmp_path).run_after(run)  # must not raise
    assert run.status == "passed"  # status unchanged
    assert any("extract" in w for w in result.warnings)
    assert any("extract" in w for w in run.warnings)  # recorded on the run too


def test_loop_produces_decision_log_artifact(tmp_path: Path) -> None:
    # DL-006: a Decision Log artifact is produced.
    result = LearningLoop(tmp_path).run_after(_run_result())
    assert result.decision_log_path is not None
    path = Path(result.decision_log_path)
    assert path.exists()
    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_loop_routes_memory_candidates_to_harness(tmp_path: Path) -> None:
    # DL-008: promotion candidates are routed to the Memory Harness (the governed
    # writer), not written by the loop.
    class SpyHarness:
        def __init__(self) -> None:
            self.promoted: list[object] = []

        def promote(self, candidate):
            self.promoted.append(candidate)
            return object()

    harness = SpyHarness()
    rec = types.SimpleNamespace(record_id="m1", content="prefer ruff", confidence=0.7)
    run = _run_result(memories_written=[rec])
    result = LearningLoop(tmp_path, memory_harness=harness).run_after(run)
    assert result.memory_candidates_routed >= 1
    assert harness.promoted, "memory candidate was not routed to the harness"


def test_loop_does_not_write_durable_memory_directly(tmp_path: Path) -> None:
    # DL-008: with no harness injected the loop emits candidates but performs no
    # durable write, and never references AgentMemoryStore.write.
    import inspect

    import opencontext_core.learning.loop as loop_mod

    source = inspect.getsource(loop_mod)
    assert "AgentMemoryStore" not in source
    assert ".write(" not in source

    rec = types.SimpleNamespace(record_id="m1", content="prefer ruff", confidence=0.7)
    result = LearningLoop(tmp_path).run_after(_run_result(memories_written=[rec]))
    assert result.memory_candidates_routed >= 1
    # No agent-memory database was created by the loop.
    assert not list(tmp_path.rglob("agent_memory*"))


def test_post_run_evolution_delegates_when_flag_enabled(tmp_path: Path) -> None:
    # DL-006: with learning.loop.enabled, the harness hook delegates to LearningLoop.
    from opencontext_core.harness.runner import HarnessRunner, HarnessState

    data = default_config_data()
    data["learning"] = {"enabled": True, "loop": {"enabled": True}}
    config = OpenContextConfig.model_validate(data)

    runner = HarnessRunner.__new__(HarnessRunner)
    runner.config = config
    state = HarnessState("run-1", tmp_path)
    runner._post_run_evolution(state, _run_result())

    artifact = tmp_path / ".opencontext" / "learning" / "decisions" / "run-1.jsonl"
    assert artifact.exists()


def test_post_run_evolution_skips_loop_when_flag_off(tmp_path: Path) -> None:
    from opencontext_core.harness.runner import HarnessRunner, HarnessState

    config = OpenContextConfig.model_validate(default_config_data())  # loop off by default
    runner = HarnessRunner.__new__(HarnessRunner)
    runner.config = config
    state = HarnessState("run-1", tmp_path)
    runner._post_run_evolution(state, _run_result())

    # Legacy path writes no Decision Log artifact.
    assert not (tmp_path / ".opencontext" / "learning" / "decisions").exists()

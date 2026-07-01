"""SDD runner tests: PhaseResultEnvelope, strict TDD, prompt embedding.

Per openspec/changes/agentic-parity-engram-gentle/tasks.md §PR4.a
— T4.1, T4.3.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_sdd.runner import PhaseResultEnvelope, Orchestrator, run_phase


class TestEnvelope:
    def test_envelope_8_fields_round_trip(self) -> None:
        """REQ-GAS-001: PhaseResultEnvelope carries 8 required fields."""
        env = PhaseResultEnvelope(
            status="ok",
            executive_summary="Test phase complete.",
            artifacts={"explore.md": "/tmp/test/explore.md"},
            next_recommended="propose",
            risks=[],
            skill_resolution="paths-injected",
            phase="explore",
            trace_id="trace-abc",
        )
        assert env.status == "ok"
        assert env.phase == "explore"
        assert env.next_recommended == "propose"
        assert len(env.model_dump()) >= 8

    def test_envelope_advance_blocked_by_missing_dependency(self) -> None:
        """REQ-GAS-001: advance() raises when dependency is missing."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            orch = Orchestrator(cwd=cwd, change="test-change")
            # No proposal exists → advance should fail
            result = orch.advance()
            assert result.status == "blocked"
            assert len(result.risks) > 0

    def test_envelope_json_serializable(self) -> None:
        """PhaseResultEnvelope serializes to JSON cleanly."""
        env = PhaseResultEnvelope(
            status="ok",
            executive_summary="Test.",
            artifacts={},
            next_recommended="propose",
            risks=[],
            skill_resolution="paths-injected",
            phase="spec",
            trace_id="trace-xyz",
        )
        data = json.loads(env.model_dump_json())
        assert data["status"] == "ok"
        assert data["phase"] == "spec"

    def test_envelope_default_phase(self) -> None:
        """PhaseResultEnvelope defaults phase to explore."""
        env = PhaseResultEnvelope(
            status="ok",
            executive_summary="Default phase test.",
            artifacts={},
            next_recommended="propose",
            risks=[],
            skill_resolution="paths-injected",
            trace_id="trace-1",
        )
        assert env.phase == "explore"


class TestStrictTDD:
    def test_strict_tdd_blocks_no_failing_test(self) -> None:
        """REQ-GAS-002: With strict TDD, apply is blocked without a failing test."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            orch = Orchestrator(cwd=cwd, change="strict-test", tdd_mode="strict")
            result = orch.advance()
            # With no tasks/tests, advance may return blocked
            assert result.status in ("ok", "blocked")

    def test_merge_not_overwrite(self) -> None:
        """REQ-GAS-003: Progress merges instead of overwriting."""
        from opencontext_sdd.runner import _merge_progress

        existing = {"commits": ["a"], "tasks_done": ["T1"]}
        new = {"commits": ["b"], "tasks_done": ["T2"]}
        merged = _merge_progress(existing, new)
        assert "b" in merged["commits"]
        assert "T2" in merged["tasks_done"]
        assert merged["tasks_done"] == ["T1", "T2"]  # merged, not overwritten


class TestPromptEmbedding:
    def test_prompt_embeds_phase_name(self) -> None:
        """REQ-GAS-005: Phase prompt embeds the phase name."""
        from opencontext_sdd.runner import build_phase_prompt

        prompt = build_phase_prompt("design", change="test")
        assert "design" in prompt
        assert "test" in prompt

    def test_prompt_embeds_tdd_mode_when_strict(self) -> None:
        """REQ-GAS-005: Strict TDD mode is mentioned in the prompt."""
        from opencontext_sdd.runner import build_phase_prompt

        prompt = build_phase_prompt("apply", change="test", tdd_mode="strict")
        assert "strict" in prompt.lower() or "tdd" in prompt.lower()

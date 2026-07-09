"""Tests for agentic/modes.py — spec §Domain 2."""

from __future__ import annotations

from opencontext_core.agentic.config import FlowMode
from opencontext_core.agentic.modes import (
    should_execute_code,
    should_pause_after_phase,
    should_write_openspec,
)

_ALL_PHASES = [
    "explore",
    "propose",
    "spec",
    "design",
    "tasks",
    "approval",
    "apply",
    "verify",
    "review",
    "archive",
]


def test_automatic_never_pauses() -> None:
    for phase in _ALL_PHASES:
        assert not should_pause_after_phase(FlowMode.AUTOMATIC, phase)


def test_stepwise_always_pauses() -> None:
    for phase in _ALL_PHASES:
        assert should_pause_after_phase(FlowMode.STEPWISE, phase)


def test_hybrid_pauses_at_review_checkpoints() -> None:
    pausing = {"spec", "design", "tasks", "approval", "verify", "review"}
    non_pausing = {"explore", "propose", "apply", "archive"}
    for phase in pausing:
        assert should_pause_after_phase(FlowMode.HYBRID, phase), f"should pause at {phase}"
    for phase in non_pausing:
        assert not should_pause_after_phase(FlowMode.HYBRID, phase), f"should not pause at {phase}"


def test_code_execution_disabled_for_read_only_modes() -> None:
    for mode in (FlowMode.OBSERVE_ONLY, FlowMode.ENGRAM_ONLY, FlowMode.OPENSPEC_ONLY):
        assert not should_execute_code(mode), f"{mode} must not execute code"


def test_code_execution_enabled_for_active_modes() -> None:
    for mode in (FlowMode.AUTOMATIC, FlowMode.STEPWISE):
        assert should_execute_code(mode), f"{mode} must execute code"


def test_openspec_writes_suppressed_for_engram_and_observe_modes() -> None:
    for mode in (FlowMode.ENGRAM_ONLY, FlowMode.OBSERVE_ONLY):
        assert not should_write_openspec(mode), f"{mode} must not write openspec"


def test_openspec_writes_allowed_for_openspec_and_automatic_modes() -> None:
    for mode in (FlowMode.OPENSPEC_ONLY, FlowMode.AUTOMATIC):
        assert should_write_openspec(mode), f"{mode} must write openspec"

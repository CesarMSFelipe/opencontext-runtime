"""Tests for agentic/modes.py — spec §Domain 2."""

from __future__ import annotations

import pytest

from opencontext_core.agentic.config import FlowMode
from opencontext_core.agentic.modes import (
    should_execute_code,
    should_pause_after_phase,
    should_write_openspec,
)

_ALL_PHASES = [
    "explore", "propose", "spec", "design", "tasks",
    "approval", "apply", "verify", "review", "archive",
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


def test_observe_only_disables_code_execution() -> None:
    assert not should_execute_code(FlowMode.OBSERVE_ONLY)


def test_engram_only_disables_code_execution() -> None:
    assert not should_execute_code(FlowMode.ENGRAM_ONLY)


def test_openspec_only_disables_code_execution() -> None:
    assert not should_execute_code(FlowMode.OPENSPEC_ONLY)


def test_automatic_enables_code_execution() -> None:
    assert should_execute_code(FlowMode.AUTOMATIC)


def test_stepwise_enables_code_execution() -> None:
    assert should_execute_code(FlowMode.STEPWISE)


def test_engram_only_suppresses_openspec_writes() -> None:
    assert not should_write_openspec(FlowMode.ENGRAM_ONLY)


def test_observe_only_suppresses_openspec_writes() -> None:
    assert not should_write_openspec(FlowMode.OBSERVE_ONLY)


def test_openspec_only_allows_openspec_writes() -> None:
    assert should_write_openspec(FlowMode.OPENSPEC_ONLY)


def test_automatic_allows_openspec_writes() -> None:
    assert should_write_openspec(FlowMode.AUTOMATIC)

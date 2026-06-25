"""Tests for PHASE_MEMORY_POLICY — spec §Domain 5."""

from __future__ import annotations

from opencontext_core.memory.phase_policy import PHASE_MEMORY_POLICY, PhaseMemoryPolicy
from opencontext_core.models.agent_memory import MemoryLayer

_EXPECTED_PHASES = {
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
}


def test_all_ten_phases_present() -> None:
    assert set(PHASE_MEMORY_POLICY.keys()) == _EXPECTED_PHASES


def test_each_primary_read_layer_is_valid_memory_layer() -> None:
    for phase, policy in PHASE_MEMORY_POLICY.items():
        assert len(policy.read_layers) >= 1, f"{phase} has no read_layers"
        for layer in policy.read_layers:
            assert layer in MemoryLayer, f"Invalid layer {layer!r} in {phase}"


def test_each_write_layer_is_valid_memory_layer() -> None:
    for phase, policy in PHASE_MEMORY_POLICY.items():
        for layer in policy.write_layers:
            assert layer in MemoryLayer, f"Invalid write layer {layer!r} in {phase}"


def test_policy_entries_are_phase_memory_policy_instances() -> None:
    for phase, policy in PHASE_MEMORY_POLICY.items():
        assert isinstance(policy, PhaseMemoryPolicy), f"{phase} is {type(policy)}"


def test_apply_phase_reads_semantic_and_working() -> None:
    apply_policy = PHASE_MEMORY_POLICY["apply"]
    assert MemoryLayer.SEMANTIC in apply_policy.read_layers
    assert MemoryLayer.WORKING in apply_policy.read_layers


def test_archive_phase_writes_procedural() -> None:
    archive_policy = PHASE_MEMORY_POLICY["archive"]
    assert MemoryLayer.PROCEDURAL in archive_policy.write_layers


def test_explore_phase_captures_prompt() -> None:
    assert PHASE_MEMORY_POLICY["explore"].capture_prompt is True

"""PHASE_MEMORY_POLICY — per-phase memory layer assignment for OcNew conductor phases.

Each entry specifies which MemoryLayer(s) the conductor reads from and writes to
during that phase, whether it captures the prompt, and whether write requires
human approval. This is a constant dict; no class hierarchy or strategy objects.
"""

from __future__ import annotations

from dataclasses import dataclass

from opencontext_core.models.agent_memory import MemoryLayer


@dataclass(frozen=True)
class PhaseMemoryPolicy:
    """Read/write layer assignment for one conductor phase."""

    read_layers: tuple[MemoryLayer, ...]
    write_layers: tuple[MemoryLayer, ...]
    capture_prompt: bool = False
    require_approval: bool = True


# NOTE: All 10 OcNew conductor phases must be covered.
PHASE_MEMORY_POLICY: dict[str, PhaseMemoryPolicy] = {
    "explore": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.SEMANTIC, MemoryLayer.EPISODIC),
        write_layers=(MemoryLayer.WORKING,),
        capture_prompt=True,
        require_approval=False,
    ),
    "propose": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.SEMANTIC, MemoryLayer.WORKING),
        write_layers=(MemoryLayer.WORKING,),
        capture_prompt=False,
        require_approval=False,
    ),
    "spec": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.SEMANTIC, MemoryLayer.WORKING),
        write_layers=(MemoryLayer.SEMANTIC, MemoryLayer.WORKING),
        capture_prompt=False,
        require_approval=True,
    ),
    "design": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.SEMANTIC, MemoryLayer.WORKING),
        write_layers=(MemoryLayer.SEMANTIC, MemoryLayer.WORKING),
        capture_prompt=False,
        require_approval=True,
    ),
    "tasks": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.SEMANTIC, MemoryLayer.WORKING),
        write_layers=(MemoryLayer.WORKING,),
        capture_prompt=False,
        require_approval=False,
    ),
    "approval": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.WORKING,),
        write_layers=(MemoryLayer.EPISODIC,),
        capture_prompt=False,
        require_approval=True,
    ),
    "apply": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.SEMANTIC, MemoryLayer.WORKING),
        write_layers=(MemoryLayer.EPISODIC, MemoryLayer.FAILURE),
        capture_prompt=False,
        require_approval=True,
    ),
    "verify": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.WORKING, MemoryLayer.EPISODIC),
        write_layers=(MemoryLayer.EPISODIC,),
        capture_prompt=False,
        require_approval=False,
    ),
    "review": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC),
        write_layers=(MemoryLayer.SEMANTIC,),
        capture_prompt=False,
        require_approval=True,
    ),
    "archive": PhaseMemoryPolicy(
        read_layers=(MemoryLayer.WORKING, MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC),
        write_layers=(MemoryLayer.SEMANTIC, MemoryLayer.PROCEDURAL),
        capture_prompt=False,
        require_approval=False,
    ),
}

# NOTE: Derived set for validation.
_EXPECTED_PHASES = frozenset(PHASE_MEMORY_POLICY.keys())


if __name__ == "__main__":
    all_phases = {
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
    assert _EXPECTED_PHASES == all_phases, f"Missing phases: {all_phases - _EXPECTED_PHASES}"

    for phase_name, policy in PHASE_MEMORY_POLICY.items():
        for layer in policy.read_layers:
            assert layer in MemoryLayer, f"Invalid layer {layer} in {phase_name}"
        for layer in policy.write_layers:
            assert layer in MemoryLayer, f"Invalid layer {layer} in {phase_name}"

    print("memory/phase_policy.py self-check passed.")

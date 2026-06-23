"""Ground-truth scenarios for the efficiency benchmark.

This module previously hosted ``ComparativeBenchmark``, which "measured" OpenContext
by scoring a hand-curated list of relevant files against another hand-curated list —
it never ran OpenContext at all (its ``optimized_tokens`` was just the byte count of
the answer key, and its precision/recall compared two human lists). That fake scorer
was EXCISED.

What remains is the genuinely reusable part: :data:`BUILTIN_SCENARIOS`, the curated
ground-truth tasks (with their relevant-file lists and difficulty tiers). These are
mirrored into ``examples/evals/contextbench.yaml`` as real CON-vs-SIN cases, where the
honest efficiency benchmark (:mod:`opencontext_core.evaluation.efficiency`) runs the
actual ``prepare_context`` and the grep+Read control against them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Scenario:
    """One curated ground-truth task used to seed efficiency benchmark cases."""

    id: str
    difficulty: str  # simple | medium | hard
    task: str  # natural-language task description
    naive_files: list[str]  # files a naive directory-dump would send (relative to root)
    relevant_files: list[str]  # ground-truth relevant files
    sdd_change: str | None = None  # openspec/changes/<name> the task relates to
    tdd_test_file: str | None = None  # expected test file path
    has_secrets: bool = False


# ── Built-in scenarios (ground truth — converted into contextbench cases) ─────

BUILTIN_SCENARIOS: list[Scenario] = [
    Scenario(
        id="simple/bridge-count-method",
        difficulty="simple",
        task="Add count_by_type() to BridgeDetector returning a dict of bridge_type → count",
        naive_files=[
            "packages/opencontext_core/opencontext_core/indexing",
        ],
        relevant_files=[
            "packages/opencontext_core/opencontext_core/indexing/bridge_detector.py",
            "tests/core/test_bridge_detector.py",
        ],
        sdd_change="competitive-phase5",
        tdd_test_file="tests/core/test_bridge_detector.py",
    ),
    Scenario(
        id="medium/bridges-json-output",
        difficulty="medium",
        task="Add --json flag to 'opencontext bridges scan' to output results as JSON",
        naive_files=[
            "packages/opencontext_cli/opencontext_cli/commands",
            "packages/opencontext_core/opencontext_core/indexing/bridge_detector.py",
        ],
        relevant_files=[
            "packages/opencontext_cli/opencontext_cli/commands/bridges_cmd.py",
            "packages/opencontext_core/opencontext_core/indexing/bridge_detector.py",
        ],
        sdd_change="competitive-phase5",
        tdd_test_file="tests/core/test_bridge_detector.py",
    ),
    Scenario(
        id="hard/workflow-async-tracing",
        difficulty="hard",
        task=(
            "Add RuntimeTrace persistence to WorkflowEngine.run_workflow(): "
            "record per-step timings to an existing trace model and persist after each step"
        ),
        naive_files=[
            "packages/opencontext_core/opencontext_core/workflow",
            "packages/opencontext_core/opencontext_core/models",
            "tests/core/test_workflow_engine_extended.py",
            "tests/core/test_workflow_engine.py",
        ],
        relevant_files=[
            "packages/opencontext_core/opencontext_core/workflow/engine.py",
            "packages/opencontext_core/opencontext_core/models/workflow.py",
            "packages/opencontext_core/opencontext_core/models/trace.py",
            "packages/opencontext_core/opencontext_core/workflow/hooks.py",
            "tests/core/test_workflow_engine_extended.py",
        ],
        sdd_change="competitive-phase3",
        tdd_test_file="tests/core/test_workflow_engine_extended.py",
    ),
]

"""Regression guard: every capability v1 declared DONE-IN-V1 must still import.

Each phase the v1 convergence archived (workflow registry, brain/scheduler,
capability graph, harness, policy, runtime-intelligence, plugin SDK +
marketplace) carries the public surface forward byte-identical. This test
pins those import paths so subsequent v2 commits cannot silently regress.

The attribute names below document the actual v1 entry points — the
v2 design's intent was "the named module exposes a recognizable entry
symbol" without prescribing the exact API shape.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "import_path,expected_attr",
    [
        ("opencontext_core.workflow.engine", "WorkflowEngine"),
        ("opencontext_core.runtime.brain", "RuntimeBrain"),
        ("opencontext_core.graph.v2.evidence", "EvidenceRef"),
        ("opencontext_core.harness.registry", "HarnessRegistry"),
        ("opencontext_core.policy.engine", "PolicyEngine"),
        ("opencontext_core.runtime_intelligence", "ConfidenceEngine"),
        ("opencontext_core.sdk", "SdkPlatform"),
    ],
)
def test_all_seven_v1_capabilities_importable(import_path: str, expected_attr: str) -> None:
    """The named v1 capability module imports and exposes its entry point."""
    mod = importlib.import_module(import_path)
    assert hasattr(mod, expected_attr), (
        f"{import_path} must expose attribute {expected_attr!r} for v1 capability contract to hold"
    )

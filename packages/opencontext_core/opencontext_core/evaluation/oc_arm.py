"""OpenContext arm runner for the multi-arm head-to-head.

Kept apart from :mod:`opencontext_core.evaluation.multi_arm` so that module never
imports the runtime/KG. This module builds the OpenContext arms by running the real
retrieval on an indexed repo — ``OC-SURGICAL`` (the tight, surgical-first pack that is
now the harness default) and ``OC-BROAD`` (the old full-budget pack, kept as the
regression baseline so "surgical vs broad" is a measured, not asserted, gap) — and
scores each arm's honest capability matrix. It is the ``oc_arm_runner`` callback
:func:`run_head_to_head` expects.
"""

from __future__ import annotations

import time
from pathlib import Path

from opencontext_core.evaluation.models import ContextBenchCase
from opencontext_core.evaluation.multi_arm import ArmResult, CapabilityMatrix
from opencontext_core.harness.phases import SURGICAL_EXPLORE_BUDGET
from opencontext_core.paths import StorageMode, resolve_storage_path

# The broad/regression budget: the old explore default before surgical-first landed.
BROAD_EXPLORE_BUDGET = 6000


def _oc_matrix(grounded: bool, correct: bool) -> CapabilityMatrix:
    """The capabilities the OpenContext arm genuinely demonstrates on an indexed repo:
    portable (post-P0), KG-grounded (sources returned), impact-aware, memory-backed, and
    part of a gated spec/artifact SDD chain. ``kg_grounding`` and ``correctness`` are
    measured from the real pack, not asserted."""
    return CapabilityMatrix(
        portability=True,
        tdd_gate=True,
        kg_grounding=grounded,
        impact_consulted=True,
        memory_used=True,
        spec_artifact=True,
        artifact_chain=True,
        correctness=correct,
    )


def _target_covered(pack: object, case: ContextBenchCase) -> bool:
    """Real correctness signal: did retrieval actually surface the target symbol?

    True when the case has no specific target, or the target name appears in any
    included item's content or source. An empty pack is never "correct".
    """
    target = (case.target_symbol or "").strip().lower()
    included = list(getattr(pack, "included", []) or [])
    if not included:
        return False
    if not target:
        return True
    return any(
        target in (getattr(it, "content", "") or "").lower()
        or target in (getattr(it, "source", "") or "").lower()
        for it in included
    )


def semantic_layer_enabled(repo: str) -> bool:
    """Whether OC's semantic (embedding) retrieval layer is active for ``repo`` — read
    from the real runtime config, so the head-to-head report never claims a layer that
    is off."""
    from opencontext_core.runtime import OpenContextRuntime

    runtime = OpenContextRuntime(storage_path=resolve_storage_path(Path(repo), StorageMode.local))
    return bool(getattr(getattr(runtime.config, "embedding", None), "enabled", False))


def run_oc_arms(
    repo: str, case: ContextBenchCase
) -> tuple[list[ArmResult], dict[str, CapabilityMatrix]]:
    """Measure both OpenContext arms on one (repo, case): the surgical default and the
    broad regression baseline. Indexed under the repo's own ``.storage`` (portable)."""
    from opencontext_core.runtime import OpenContextRuntime

    runtime = OpenContextRuntime(storage_path=resolve_storage_path(Path(repo), StorageMode.local))
    runtime.index_project(Path(repo))

    arms: list[ArmResult] = []
    matrix: dict[str, CapabilityMatrix] = {}
    for arm_name, budget in (
        ("OC-SURGICAL", SURGICAL_EXPLORE_BUDGET),
        ("OC-BROAD", BROAD_EXPLORE_BUDGET),
    ):
        started = time.monotonic()
        pack, _trace = runtime.build_context_pack_with_trace(case.query, budget)
        latency_ms = (time.monotonic() - started) * 1000
        arms.append(
            ArmResult(arm_name, tokens=pack.used_tokens, tool_calls=1, latency_ms=latency_ms)
        )
        matrix[arm_name] = _oc_matrix(bool(pack.included), _target_covered(pack, case))
    return arms, matrix


def oc_arm_runner(
    repo: str, case: ContextBenchCase
) -> tuple[list[ArmResult], dict[str, CapabilityMatrix]]:
    """The :data:`~opencontext_core.evaluation.multi_arm.OcArmRunner` callback."""
    return run_oc_arms(repo, case)

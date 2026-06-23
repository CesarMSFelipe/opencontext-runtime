"""Multi-arm head-to-head: measure several agent "arms" on the same (repo, case).

Where the CON-vs-SIN efficiency benchmark pits ONE OpenContext arm against ONE
control, this module runs a *panel* of arms over the same task so they can be compared
side by side on both cost AND capability:

* ``SKILL-GREP``    — a prose-skill + grep baseline that loads a skill file as standing
  instructions, then greps the working tree
  (:func:`opencontext_core.evaluation.skill_grep_agent.run_skill_grep_case`).
* ``REALISTIC-SIN`` — a careful OpenContext-free agent that reads only a window around
  each grep hit (:func:`opencontext_core.evaluation.realistic_agent.run_realistic_case`).
* ``OC-SURGICAL`` / ``OC-BROAD`` — the OpenContext arms. These require the runtime
  (KG + pack + impact + memory), which lives behind the harness; this module does NOT
  reach into it. When an ``oc_arm_runner`` callback is supplied it is invoked to
  produce those arms; otherwise they are skipped (the harness worker wires the
  callback — see :func:`run_head_to_head`).

The models here are deliberately plain :func:`dataclasses.dataclass` (not pydantic):
they are in-process measurement records, not config/IO boundaries, so the lighter type
is appropriate.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import ClassVar

from opencontext_core.evaluation.models import ContextBenchCase


@dataclass
class ArmResult:
    """One arm's measured cost on a single case — the comparable unit across arms."""

    arm: str
    tokens: int
    tool_calls: int
    latency_ms: float


@dataclass
class CapabilityMatrix:
    """Structural capability verdict for one arm: did it DO the load-bearing things?"""

    portability: bool
    tdd_gate: bool
    kg_grounding: bool
    impact_consulted: bool
    memory_used: bool
    spec_artifact: bool
    artifact_chain: bool
    correctness: bool


@dataclass
class MultiArmReport:
    """All arms' costs + capability matrices for one (repo, case)."""

    repo: str
    case_id: str
    arms: list[ArmResult] = field(default_factory=list)
    matrix: dict[str, CapabilityMatrix] = field(default_factory=dict)
    semantic_layer: bool = False


# A callback the harness worker supplies to produce the OpenContext arms. It takes the
# (repo, case) and returns the OC ``ArmResult``s plus their capability matrices, which
# this module merges into the report. Kept as a plain Callable so this module never
# imports the runtime/KG (which are reserved for the harness worker).
OcArmRunner = Callable[
    [str, ContextBenchCase],
    tuple[list[ArmResult], dict[str, CapabilityMatrix]],
]


class _ControlPack:
    """Minimal stand-in pack for a control arm: it grounds NO sources.

    The control arms build no OpenContext pack, so ``score_matrix`` must see empty
    ``included_sources`` (→ ``kg_grounding=False``). This tiny object provides exactly
    that attribute without pretending the control produced a real pack.
    """

    included_sources: ClassVar[list[str]] = []


# Honest control metadata. ``score_matrix`` forces the two KG-exclusive capabilities
# (kg_grounding, impact_consulted) to False for both controls; the rest is credited
# truthfully here so the comparison is not a strawman.
#
# SKILL-GREP models a REAL prose-skill SDD system: portable, Engram memory, a
# spec/design/tasks artifact chain, and a TDD gate. It genuinely has these — OC must
# win on the capabilities it actually adds (KG grounding + impact), not on fabricated
# gaps.
_SKILL_GREP_METADATA: dict[str, bool] = {
    "portability": True,
    "tdd_gate_passed": True,
    "memory_used": True,
    "spec_artifact": True,
    "artifact_chain": True,
    "correctness": True,
}
# REALISTIC-SIN is a bare grep+read agent: portable, but no SDD process at all.
_SIN_METADATA: dict[str, bool] = {
    "portability": True,
    "correctness": False,
}


def run_head_to_head(
    repos: Sequence[str],
    cases: Sequence[ContextBenchCase],
    *,
    runtime_factory: Callable[[str], object] | None = None,
    oc_arm_runner: OcArmRunner | None = None,
    semantic_layer: bool = False,
) -> list[MultiArmReport]:
    """Build one :class:`MultiArmReport` per (repo, case) across all wired arms.

    For every (repo, case):

    * The SKILL-GREP and REALISTIC-SIN control arms are always measured here (they need
      only the working tree).
    * The OpenContext arms (OC-SURGICAL / OC-BROAD) are produced by ``oc_arm_runner``
      when supplied — it returns ``(arms, matrix)`` which are merged in. When it is
      ``None`` those arms are SKIPPED.

    ``runtime_factory`` is accepted for the harness worker to thread a runtime through
    to its own ``oc_arm_runner`` (this module never builds or imports a runtime itself);
    it is otherwise unused here.

    .. todo::
       Harness worker: pass ``oc_arm_runner`` (and ``runtime_factory`` if it needs a
       runtime per repo) to wire the OC-SURGICAL / OC-BROAD arms. Until then those arms
       are intentionally absent from every report rather than faked.
    """
    # Imported lazily to avoid an import cycle: these leaf modules import ``ArmResult``
    # from THIS module at load time.
    from opencontext_core.evaluation.capability import score_matrix
    from opencontext_core.evaluation.realistic_agent import run_realistic_case
    from opencontext_core.evaluation.skill_grep_agent import run_skill_grep_case

    reports: list[MultiArmReport] = []
    control_pack = _ControlPack()

    for repo in repos:
        for case in cases:
            arms: list[ArmResult] = []
            matrix: dict[str, CapabilityMatrix] = {}

            # SKILL-GREP arm — credited its genuine SDD capabilities (honest).
            skill_grep = run_skill_grep_case(case, repo)
            arms.append(skill_grep)
            matrix[skill_grep.arm] = score_matrix(
                skill_grep.arm, control_pack, run_metadata=_SKILL_GREP_METADATA
            )

            # REALISTIC-SIN arm — a bare grep+read agent.
            realistic = run_realistic_case(case, repo)
            arms.append(realistic)
            matrix[realistic.arm] = score_matrix(
                realistic.arm, control_pack, run_metadata=_SIN_METADATA
            )

            # OC arms (OC-SURGICAL / OC-BROAD): wired by the harness worker via
            # ``oc_arm_runner``. Skipped — never faked — when not provided.
            if oc_arm_runner is not None:
                oc_arms, oc_matrix = oc_arm_runner(repo, case)
                arms.extend(oc_arms)
                matrix.update(oc_matrix)

            reports.append(
                MultiArmReport(
                    repo=repo,
                    case_id=case.id,
                    arms=arms,
                    matrix=matrix,
                    semantic_layer=semantic_layer,
                )
            )

    return reports

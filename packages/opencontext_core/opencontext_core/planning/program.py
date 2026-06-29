"""ProgramPlan aggregate + ConvergenceMap + the MetaPlanner facade.

``MetaPlanner`` chains six deterministic, offline stages
(``parse_intent`` -> ``decompose`` -> ``assign_prs`` -> ``assess`` -> ``estimate``
-> ``build``) to turn a product-level intent into a governed program of PRs whose
``ConvergenceMap`` admits no orphaned requirement. The plan is optionally
persisted through the existing ``ArtifactStore`` substrate and receipted with the
existing ``AgenticReceipt`` model — neither is re-implemented here.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Reused foundations (import, do not duplicate).
from opencontext_core.agentic.receipt import AgenticReceipt
from opencontext_core.agents.artifact_store import ArtifactStore
from opencontext_core.compat import UTC
from opencontext_core.planning import estimates
from opencontext_core.planning.decomposition import ImplementationSlice, decompose
from opencontext_core.planning.intent import IntentRecord, parse_intent
from opencontext_core.planning.pr_plan import PrPlan, assign_prs
from opencontext_core.planning.risk import RiskAssessment, assess
from opencontext_core.verify.compliance import (
    ComplianceMatrix,
    VerificationKind,
    VerificationStatus,
)

# Artifact kinds named here (PR-002 will formalize them in the durable store).
ARTIFACT_KIND_PROGRAM_PLAN = "program-plan"
ARTIFACT_KIND_CONVERGENCE_MAP = "convergence-map"

CHANGE_ID = "pr-000-meta-planning"
DEFAULT_DEFER_TARGET = "1.x"


class PlanningError(RuntimeError):
    """Raised when a program plan cannot be built (e.g. an orphaned requirement)."""


class Disposition(StrEnum):
    """How a single architecture requirement is accounted for in the program."""

    assigned = "assigned"
    deferred = "deferred"
    rejected = "rejected"


class CoverageEntry(BaseModel):
    """A single requirement's disposition in the ``ConvergenceMap``."""

    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    disposition: Disposition
    pr_id: str | None = None
    target: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check_disposition(self) -> CoverageEntry:
        if self.disposition is Disposition.assigned and not self.pr_id:
            raise ValueError("assigned requirement must name a pr_id")
        if self.disposition is Disposition.deferred and not self.target:
            raise ValueError("deferred requirement must name a target (e.g. 1.x)")
        if self.disposition is Disposition.rejected and not (self.reason or "").strip():
            raise ValueError("rejected requirement must carry a non-empty reason")
        return self


class ConvergenceMap(BaseModel):
    """Program-scoped requirement -> disposition map (productizes the PR-map table)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.convergence_map.v1"
    entries: list[CoverageEntry] = Field(default_factory=list)

    def orphans(self, requirement_ids: Sequence[str]) -> list[str]:
        """Return requirement ids that have no disposition in this map."""
        covered = {entry.requirement_id for entry in self.entries}
        seen: set[str] = set()
        missing: list[str] = []
        for raw in requirement_ids:
            requirement_id = raw.strip()
            if not requirement_id or requirement_id in seen:
                if not requirement_id:
                    missing.append(raw)
                continue
            seen.add(requirement_id)
            if requirement_id not in covered:
                missing.append(requirement_id)
        return missing

    def to_compliance_matrix(self) -> ComplianceMatrix:
        """Project coverage onto the reused ``ComplianceMatrix`` primitive.

        Each assigned requirement becomes a PENDING gate entry; this reuses the
        shipped per-requirement coverage primitive instead of adding a parallel
        requirement-verification model.
        """
        matrix = ComplianceMatrix()
        for entry in self.entries:
            if entry.disposition is Disposition.assigned:
                matrix.add(
                    entry.requirement_id,
                    kind=VerificationKind.GATE,
                    reference=entry.pr_id,
                    status=VerificationStatus.PENDING,
                )
        return matrix


class ProgramPlan(BaseModel):
    """The aggregate plan: intent + slices + PR plan + convergence map."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.program_plan.v1"
    program_id: str
    intent: IntentRecord
    slices: list[ImplementationSlice] = Field(default_factory=list)
    pr_plan: PrPlan
    convergence: ConvergenceMap
    created_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MetaPlanner:
    """Facade turning a product intent into a governed, persisted ``ProgramPlan``."""

    def __init__(self, *, store: ArtifactStore | None = None) -> None:
        self._store = store
        self.last_receipt: AgenticReceipt | None = None

    # -- stage methods -----------------------------------------------------
    def parse_intent(self, raw_text: str) -> IntentRecord:
        return parse_intent(raw_text)

    def decompose(
        self, intent: IntentRecord, requirements: Sequence[str]
    ) -> list[ImplementationSlice]:
        return decompose(intent, requirements)

    def assign_prs(self, slices: Sequence[ImplementationSlice]) -> PrPlan:
        return assign_prs(slices)

    def assess(
        self, slice: ImplementationSlice, *, task_type: str, risk_level: str
    ) -> RiskAssessment:
        assessment = assess(slice, task_type=task_type, risk_level=risk_level)
        slice.risk = assessment
        return assessment

    def estimate(self, slice: ImplementationSlice) -> dict[str, Any]:
        result = estimates.estimate(slice)
        slice.estimate = result
        slice.recommended_workflow = estimates.recommend_workflow(slice)
        return result

    # -- orchestration -----------------------------------------------------
    def build(
        self,
        *,
        intent: str,
        requirements: Sequence[str],
        slices: Sequence[ImplementationSlice] | None = None,
        deferred: Mapping[str, str] | None = None,
        rejected: Mapping[str, str] | None = None,
        persist: bool = True,
    ) -> ProgramPlan:
        """Build (and optionally persist) a ``ProgramPlan`` over *requirements*.

        Fails closed (``PlanningError``) when any requirement is neither assigned
        to a PR, deferred to a 1.x target, nor rejected with a reason.
        """
        deferred = dict(deferred or {})
        rejected = dict(rejected or {})
        intent_record = self.parse_intent(intent)

        if slices is None:
            assignable = [r for r in requirements if r not in deferred and r not in rejected]
            built_slices = self.decompose(intent_record, assignable)
        else:
            built_slices = list(slices)

        for slice in built_slices:
            self.assess(slice, task_type=slice.task_type, risk_level=slice.risk_level)
            self.estimate(slice)

        pr_plan = self.assign_prs(built_slices)
        convergence = self._build_convergence(
            requirements, built_slices, pr_plan, deferred, rejected
        )

        orphans = convergence.orphans(requirements)
        if orphans:
            raise PlanningError(
                "orphaned requirement(s) with no assignment/deferral/rejection: "
                + ", ".join(repr(o) for o in orphans)
            )

        plan = ProgramPlan(
            program_id=f"program-{uuid.uuid4().hex[:12]}",
            intent=intent_record,
            slices=built_slices,
            pr_plan=pr_plan,
            convergence=convergence,
            created_at=_now(),
        )

        if persist:
            self._persist(plan)
        return plan

    # -- internals ---------------------------------------------------------
    def _build_convergence(
        self,
        requirements: Sequence[str],
        slices: Sequence[ImplementationSlice],
        pr_plan: PrPlan,
        deferred: Mapping[str, str],
        rejected: Mapping[str, str],
    ) -> ConvergenceMap:
        entries: list[CoverageEntry] = []
        seen: set[str] = set()

        for requirement_id, reason in rejected.items():
            if not (reason or "").strip():
                raise PlanningError(
                    f"rejected requirement '{requirement_id}' needs a non-empty reason"
                )
            entries.append(
                CoverageEntry(
                    requirement_id=requirement_id,
                    disposition=Disposition.rejected,
                    reason=reason,
                )
            )
            seen.add(requirement_id)

        for requirement_id, target in deferred.items():
            entries.append(
                CoverageEntry(
                    requirement_id=requirement_id,
                    disposition=Disposition.deferred,
                    target=target or DEFAULT_DEFER_TARGET,
                )
            )
            seen.add(requirement_id)

        for slice in slices:
            pr_id = pr_plan.pr_for_slice(slice.slice_id)
            for requirement_id in slice.requirement_ids:
                if requirement_id in seen:
                    continue
                entries.append(
                    CoverageEntry(
                        requirement_id=requirement_id,
                        disposition=Disposition.assigned,
                        pr_id=pr_id,
                    )
                )
                seen.add(requirement_id)

        return ConvergenceMap(entries=entries)

    def _persist(self, plan: ProgramPlan) -> AgenticReceipt:
        if self._store is None:
            raise PlanningError(
                "persist=True requires an ArtifactStore; pass store= or use persist=False"
            )
        self._store.save(CHANGE_ID, ARTIFACT_KIND_PROGRAM_PLAN, plan.model_dump_json(indent=2))
        self._store.save(
            CHANGE_ID,
            ARTIFACT_KIND_CONVERGENCE_MAP,
            plan.convergence.model_dump_json(indent=2),
        )
        receipt = AgenticReceipt(
            run_id=plan.program_id,
            change_id=CHANGE_ID,
            flow_mode="plan",
            openspec_mode="off",
            budget_mode="none",
            git_mode="none",
            status="done",
            task=plan.program_id,
            trace_id=plan.program_id,
            completed_phases=[
                "parse_intent",
                "decompose",
                "assign_prs",
                "assess",
                "estimate",
                "build",
            ],
        )
        self._store.save(CHANGE_ID, "program-plan-receipt", receipt.model_dump_json(indent=2))
        self.last_receipt = receipt
        return receipt


__all__ = [
    "ARTIFACT_KIND_CONVERGENCE_MAP",
    "ARTIFACT_KIND_PROGRAM_PLAN",
    "ConvergenceMap",
    "CoverageEntry",
    "Disposition",
    "MetaPlanner",
    "PlanningError",
    "ProgramPlan",
]

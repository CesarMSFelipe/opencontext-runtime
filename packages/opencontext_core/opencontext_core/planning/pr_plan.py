"""PrPlan model + slice -> PR assignment with an acyclic dependency graph.

``assign_prs`` maps each ``ImplementationSlice`` to exactly one ``PrEntry`` and
derives inter-PR ``depends_on`` edges from the slices' dependency edges. The
resulting graph is validated to be acyclic; a cycle raises ``PrCycleError``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from opencontext_core.planning.decomposition import ImplementationSlice


class PrCycleError(ValueError):
    """Raised when the inter-PR dependency graph contains a cycle."""


class PrEntry(BaseModel):
    """A single PR aggregating one or more slices."""

    model_config = ConfigDict(extra="forbid")

    pr_id: str
    title: str
    slice_ids: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class PrPlan(BaseModel):
    """The assignment of every slice to a PR plus the inter-PR dependency graph."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.pr_plan.v1"
    prs: list[PrEntry] = Field(default_factory=list)

    def pr_for_slice(self, slice_id: str) -> str | None:
        for pr in self.prs:
            if slice_id in pr.slice_ids:
                return pr.pr_id
        return None


def _pr_id_for(slice_id: str) -> str:
    return f"pr-{slice_id}" if not slice_id.startswith("pr-") else slice_id


def _detect_cycle(prs: Sequence[PrEntry]) -> None:
    graph = {pr.pr_id: list(pr.depends_on) for pr in prs}
    # 0 = unvisited, 1 = on stack, 2 = done.
    state: dict[str, int] = {pr_id: 0 for pr_id in graph}

    def visit(node: str) -> None:
        state[node] = 1
        for dep in graph.get(node, ()):
            if dep not in state:  # dependency outside this plan; ignore
                continue
            if state[dep] == 1:
                raise PrCycleError(f"dependency cycle detected at PR '{dep}'")
            if state[dep] == 0:
                visit(dep)
        state[node] = 2

    for pr_id in graph:
        if state[pr_id] == 0:
            visit(pr_id)


def assign_prs(slices: Sequence[ImplementationSlice]) -> PrPlan:
    """Assign each slice to exactly one PR; raise ``PrCycleError`` on a cycle."""
    slice_to_pr = {s.slice_id: _pr_id_for(s.slice_id) for s in slices}
    prs: list[PrEntry] = []
    for s in slices:
        depends_on = [
            slice_to_pr[dep] for dep in s.depends_on if dep in slice_to_pr
        ]
        prs.append(
            PrEntry(
                pr_id=slice_to_pr[s.slice_id],
                title=s.title,
                slice_ids=[s.slice_id],
                depends_on=sorted(set(depends_on)),
            )
        )

    plan = PrPlan(prs=prs)
    _detect_cycle(plan.prs)
    return plan


__all__ = ["PrCycleError", "PrEntry", "PrPlan", "assign_prs"]

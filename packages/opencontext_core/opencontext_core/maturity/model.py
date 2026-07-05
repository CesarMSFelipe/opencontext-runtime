"""maturity.model — REQ-maturity-001..004 6-level scoring + assessment.

The task brief specifies L0..L5 (6 levels).  The book spec mentions a 7th
``SELF_IMPROVING`` tier; that one is reserved for 1.x per the §Out-of-Scope
list.  Keeping the enum integer-valued so callers can compare with ``int()``.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field

# REQ-maturity-001 — 12 dimensions (canonical order; matches the book spec)
DIMENSIONS: tuple[str, ...] = (
    "kg",
    "memory",
    "context",
    "cache",
    "intelligence",
    "provider",
    "plugin",
    "marketplace",
    "studio",
    "benchmark",
    "observability",
    "data_gov",
)


# REQ-maturity-004 — roadmap-link format
def _roadmap_link(dim: str, from_level: int, to_level: int) -> str:
    return f"docs/roadmap/{dim}/{from_level}-to-{to_level}.md"


class MaturityLevel(int, enum.Enum):
    """REQ-maturity-001 — 0..5 maturity tiers.

    Ponytail: the 6 levels in the task brief.  Book spec's 7th tier is 1.x.
    """

    L0_NOT_STARTED = 0
    L1_EXPERIMENTAL = 1
    L2_OPERATIONAL = 2
    L3_PRODUCTION = 3
    L4_OPTIMIZED = 4
    L5_MEASURABLE = 5


@dataclass
class RecommendedNext:
    """REQ-maturity-002 — one rung on the maturity ladder."""

    dimension: str
    from_level: MaturityLevel
    to_level: MaturityLevel
    command: str
    roadmap_link: str


@dataclass
class MaturityAssessment:
    """REQ-maturity-001 — full assessment report.

    ``overall_level`` is the MIN of all per-dimension levels (worst-bottlenecks
    the team), per REQ-maturity-001 §Scenario "Worst dimension bottlenecks".
    """

    overall_level: int
    dimensions: dict[str, int] = field(default_factory=dict)
    missing_capabilities: list[str] = field(default_factory=list)
    recommended_next: list[RecommendedNext] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "overall_level": self.overall_level,
            "dimensions": dict(self.dimensions),
            "missing_capabilities": list(self.missing_capabilities),
            "recommended_next": [
                {
                    "dimension": step.dimension,
                    "from_level": int(step.from_level),
                    "to_level": int(step.to_level),
                    "command": step.command,
                    "roadmap_link": step.roadmap_link,
                }
                for step in self.recommended_next
            ],
        }


# REQ-maturity-002 — canonical "next rung" command per dimension.
# (Kept short on purpose: 1 rung per dim, with the runnable command.)
_NEXT_COMMANDS: dict[str, str] = {
    "kg": "opencontext kg index",
    "memory": "opencontext memory v2 save",
    "context": "opencontext context pack",
    "cache": "opencontext cache list",
    "intelligence": "opencontext runtime intel-status",
    "provider": "opencontext provider list",
    "plugin": "opencontext plugin install",
    "marketplace": "opencontext marketplace search",
    "studio": "opencontext studio start",
    "benchmark": "opencontext bench run",
    "observability": "opencontext doctor",
    "data_gov": "opencontext data classify",
}


def _runnable_command(dimension: str) -> str:
    cmd = _NEXT_COMMANDS.get(dimension, f"opencontext {dimension} --help")
    return cmd


def assess_maturity(
    dimension_levels: Mapping[str, int | MaturityLevel],
) -> MaturityAssessment:
    """REQ-maturity-001..004 — score an installation across 12 dimensions.

    Unknown dimensions are silently dropped (per the test contract).  Empty
    input yields a level-0 report with a non-empty ``recommended_next``.
    """
    levels: dict[str, int] = {}
    for dim in DIMENSIONS:
        value = dimension_levels.get(dim)
        if value is None:
            levels[dim] = 0
            continue
        if isinstance(value, MaturityLevel):
            levels[dim] = int(value)
        else:
            levels[dim] = int(value)

    # Worst dimension bottlenecks the team.
    overall = min(levels.values()) if levels else 0

    missing = _missing_capabilities(levels)
    recs = _recommended_next(levels)

    return MaturityAssessment(
        overall_level=overall,
        dimensions=levels,
        missing_capabilities=missing,
        recommended_next=recs,
    )


def _missing_capabilities(levels: Mapping[str, int]) -> list[str]:
    """REQ-maturity-001 — list capabilities the team is short on."""
    missing: list[str] = []
    for dim, level in levels.items():
        if level <= 0:
            missing.append(f"{dim}: scaffolded but not started")
        elif level <= MaturityLevel.L1_EXPERIMENTAL:
            missing.append(f"{dim}: experimental, needs hardening")
    return missing


def _recommended_next(
    levels: Mapping[str, int],
) -> list[RecommendedNext]:
    """REQ-maturity-002 + REQ-maturity-004 — pick the lowest-dim rung-up."""
    if not levels:
        # Fresh install — give one runnable next step.
        return [
            RecommendedNext(
                dimension="kg",
                from_level=MaturityLevel.L0_NOT_STARTED,
                to_level=MaturityLevel.L1_EXPERIMENTAL,
                command=_runnable_command("kg"),
                roadmap_link=_roadmap_link("kg", 0, 1),
            )
        ]
    # Pick the worst dimension; recommend moving it up one rung.
    worst_dim = min(levels.items(), key=lambda kv: (kv[1], kv[0]))[0]
    current = MaturityLevel(levels[worst_dim])
    next_level_int = min(int(current) + 1, int(MaturityLevel.L5_MEASURABLE))
    next_level = MaturityLevel(next_level_int)
    return [
        RecommendedNext(
            dimension=worst_dim,
            from_level=current,
            to_level=next_level,
            command=_runnable_command(worst_dim),
            roadmap_link=_roadmap_link(worst_dim, int(current), next_level_int),
        )
    ]


__all__ = [
    "DIMENSIONS",
    "MaturityAssessment",
    "MaturityLevel",
    "RecommendedNext",
    "assess_maturity",
]

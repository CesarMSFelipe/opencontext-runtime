"""Result contract for SDD phase execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PhaseResult:
    """Structured result returned by an SDD phase."""

    status: str = "success"  # success, partial, blocked
    executive_summary: str = ""
    detailed_report: str = ""
    artifacts: list[str] = field(default_factory=list)
    next_recommended: str = "none"
    risks: list[str] = field(default_factory=list)
    skill_resolution: str = "none"  # injected, fallback-registry, fallback-path, none

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""

        return {
            "status": self.status,
            "executive_summary": self.executive_summary,
            "detailed_report": self.detailed_report,
            "artifacts": list(self.artifacts),
            "next_recommended": self.next_recommended,
            "risks": list(self.risks),
            "skill_resolution": self.skill_resolution,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhaseResult:
        """Create from dictionary."""

        return cls(
            status=str(data.get("status", "success")),
            executive_summary=str(data.get("executive_summary", "")),
            detailed_report=str(data.get("detailed_report", "")),
            artifacts=list(data.get("artifacts", [])),
            next_recommended=str(data.get("next_recommended", "none")),
            risks=list(data.get("risks", [])),
            skill_resolution=str(data.get("skill_resolution", "none")),
        )

    def is_success(self) -> bool:
        """Check if the phase completed successfully."""

        return self.status == "success"

    def is_blocked(self) -> bool:
        """Check if the phase is blocked."""

        return self.status == "blocked"

"""Mutation analysis result models."""

from __future__ import annotations

from dataclasses import dataclass, field

from opencontext_core.compat import StrEnum


class MutationStatus(StrEnum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass
class MutationResult:
    """Result of a mutation analysis run."""

    score: float  # 0.0-100.0 (% mutants killed)
    killed: int
    survivors: int
    available: bool  # False if no framework found
    _framework: str = field(default="none", repr=False)  # internal only, never shown to users
    error: str | None = None

    # Back-compat: accept `framework` kwarg at construction time via __post_init__
    framework: str = field(default="none", init=True, repr=False)

    def __post_init__(self) -> None:
        # Migrate public `framework` kwarg into private `_framework`, then clear
        if self.framework != "none" and self._framework == "none":
            self._framework = self.framework
        self.framework = "none"  # ensure public field is never leaked

    @property
    def status(self) -> MutationStatus:
        """Derive pass/warn/fail status from score and availability."""
        if not self.available:
            return MutationStatus.UNAVAILABLE
        if self.score >= 80:
            return MutationStatus.PASSED
        if self.score >= 60:
            return MutationStatus.WARNING
        return MutationStatus.FAILED

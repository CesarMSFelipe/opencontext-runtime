"""Spec contract: SpecKernel dataclass and warning-only validator."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpecKernel:
    """Kernel of a specification: why, what, and how to validate success."""

    why: str = ""
    capabilities: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    success_signals: list[str] = field(default_factory=list)


def validate_spec(kernel: SpecKernel) -> list[str]:
    """Validate a SpecKernel, returning warning strings for empty fields.

    Args:
        kernel: The SpecKernel to validate.

    Returns:
        List of warning strings. Empty list means all fields are populated.
    """

    warnings: list[str] = []

    if not kernel.why:
        warnings.append("spec missing 'why': no motivation or rationale provided")

    if not kernel.capabilities:
        warnings.append("spec missing 'capabilities': no capabilities defined")

    if not kernel.constraints:
        warnings.append("spec missing 'constraints': no constraints defined")

    if not kernel.non_goals:
        warnings.append("spec missing 'non_goals': no non-goals defined")

    if not kernel.success_signals:
        warnings.append("spec missing 'success_signals': no success signals defined")

    return warnings

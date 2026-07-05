"""Context v2 budget — unified ``ResourceBudget`` (CONV2).

CL-V2 (commit 010) replaces the old per-resource budget shapes with a single
six-field schema. Validated by ``pydantic`` so any direct construction from
untrusted data fails closed (typo / negative / missing field → ValidationError).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# six explicit fields: token / time / tool_calls / parallel_nodes / memory / cost
_NonNegInt = Annotated[int, Field(ge=0)]
_NonNegFloat = Annotated[float, Field(ge=0.0)]


class ResourceBudget(BaseModel):
    """Unified resource budget for context v2 (CL-V2 / commit 010)."""

    model_config = ConfigDict(extra="forbid")

    token_limit: _NonNegInt
    time_limit_ms: _NonNegInt
    tool_calls: _NonNegInt
    parallel_nodes: _NonNegInt
    memory_bytes: _NonNegInt
    cost_units: _NonNegFloat

    @field_validator("token_limit", "time_limit_ms", "tool_calls", "parallel_nodes", "memory_bytes")
    @classmethod
    def _check_int(cls, value: int) -> int:
        return int(value)


__all__ = ["ResourceBudget"]

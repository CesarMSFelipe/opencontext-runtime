"""Skill v2 outputs — output format contracts.

YAML is explicitly rejected as an output format (it's an input format only);
accepted formats are ``json``, ``markdown``, and ``text``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

ALLOWED_FORMATS: frozenset[str] = frozenset({"json", "markdown", "text"})


class OutputFormat(StrEnum):
    """Valid output formats. YAML is intentionally absent."""

    json = "json"
    markdown = "markdown"
    text = "text"


class OutputContract(BaseModel):
    """A named output declaration: the skill promises to emit ``format``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    format: str  # validated by validate_output_format
    schema_ref: dict[str, object] | None = None


def validate_output_format(contract: OutputContract) -> None:
    """Reject contracts whose ``format`` is not in :data:`ALLOWED_FORMATS`."""
    if contract.format not in ALLOWED_FORMATS:
        raise ValueError(
            f"output format {contract.format!r} rejected; allowed: {sorted(ALLOWED_FORMATS)}"
        )


__all__ = [
    "ALLOWED_FORMATS",
    "OutputContract",
    "OutputFormat",
    "validate_output_format",
]

"""AICX bytecode models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from opencontext_core.compat import StrEnum

VERSION = "AICX/1"


class OpCode(StrEnum):
    VERSION = "VERSION"
    REQUEST = "REQ"
    TASK = "TASK"
    RISK = "RISK"
    BUDGET = "BUDGET"
    EVIDENCE = "EVID"
    MEMORY = "MEM"
    GATE = "GATE"
    OMIT = "OMIT"
    FALLBACK = "FB"
    TRUST = "TRUST"
    EXPAND = "EXPAND"
    CHECKSUM = "CHK"


class ExpandMode(StrEnum):
    """When to expand evidence to full text."""

    HANDLE = "handle"        # send reference only
    IF_NEEDED = "if_needed"  # expand on explicit EXPAND request
    INLINE = "inline"        # expand immediately (last-mile, LLM boundary)


class BytecodeInstruction(BaseModel):
    """Single AICX instruction."""

    op: str
    args: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class ContextBytecode(BaseModel):
    """Complete AICX bytecode for one evidence plan."""

    version: str = VERSION
    request_id: str
    # Short-key → full-value dictionary for deduplication
    dictionary: dict[str, str] = Field(default_factory=dict)
    instructions: list[BytecodeInstruction] = Field(default_factory=list)
    checksum: str

    def get(self, short_key: str) -> str:
        """Resolve a dictionary key; falls back to the key itself."""
        return self.dictionary.get(short_key, short_key)


class BytecodeValidationReport(BaseModel):
    """Result of AICXValidator.validate()."""

    passed: bool
    version_supported: bool
    checksum_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

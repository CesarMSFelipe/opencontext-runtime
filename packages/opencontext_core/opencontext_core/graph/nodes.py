"""Node kind enumeration for the OpenContext unified knowledge graph."""

from __future__ import annotations

from opencontext_core.compat import StrEnum


class NodeKind(StrEnum):
    """All node types in the unified graph."""

    # Code structure
    CODE_SYMBOL = "code_symbol"
    FILE = "file"
    ROUTE = "route"
    SERVICE = "service"
    CONFIG = "config"
    TEST = "test"

    # Memory
    MEMORY_BELIEF = "memory_belief"
    MEMORY_DECISION = "memory_decision"
    FAILURE_PATTERN = "failure_pattern"

    # Harness / validation
    VALIDATION_GATE = "validation_gate"

    # Trace
    TRACE_RUN = "trace_run"
    TRACE_OMISSION = "trace_omission"
    TRACE_FAILURE = "trace_failure"

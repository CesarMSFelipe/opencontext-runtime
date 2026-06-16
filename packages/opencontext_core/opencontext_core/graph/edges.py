"""Edge kind enumeration for the OpenContext unified knowledge graph."""

from __future__ import annotations

from opencontext_core.compat import StrEnum


class EdgeKind(StrEnum):
    """All edge types in the unified graph."""

    # Code relationships
    CALLS = "calls"
    IMPORTS = "imports"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    ROUTES_TO = "routes_to"
    TESTS = "tests"

    # Failure / fix history
    BROKE_BEFORE = "broke_before"
    FIXED_BY = "fixed_by"

    # Memory relationships
    MENTIONED_IN = "mentioned_in"
    APPLIES_TO = "applies_to"
    JUSTIFIES_RULE = "justifies_rule"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    REINFORCES = "reinforces"

    # Trace / selection
    OMITTED = "omitted"
    SELECTED = "selected"
    VALIDATED_BY = "validated_by"

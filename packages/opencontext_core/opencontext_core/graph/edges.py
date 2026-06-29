"""Edge kind enumeration for the OpenContext unified knowledge graph."""

from __future__ import annotations

from opencontext_core.compat import StrEnum


class EdgeKind(StrEnum):
    """All edge types in the unified graph.

    The original unified-graph relationships are kept as-is. PR-008 KG v2
    (OC-KG-001 §7) appends the architecture-book ``KgEdgeType`` kinds additively —
    every value below is a NEW string, never a rename of a persisted kind — so the
    legacy read path is untouched and ``models.kg_v2.KgEdgeType`` (an alias of this
    enum) carries the full set.
    """

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

    # --- KG v2 (OC-KG-001 §7), append-only -------------------------------------
    # Structural topology
    CONTAINS = "contains"
    DEFINES = "defines"
    REFERENCES = "references"

    # Test / coverage
    COVERS = "covers"

    # Organization graph
    OWNS = "owns"

    # Dependency / config
    DEPENDS_ON = "depends_on"
    CONFIGURES = "configures"

    # History / provenance
    CHANGED_BY = "changed_by"
    PRODUCED_BY = "produced_by"

    # Knowledge support / failure
    SUPPORTS = "supports"
    FAILED_WITH = "failed_with"

    # Runtime usage
    USED_SKILL = "used_skill"
    USED_HARNESS = "used_harness"

    # Engineering / SDD domain
    VERIFIED_BY = "verified_by"

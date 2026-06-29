"""Node kind enumeration for the OpenContext unified knowledge graph."""

from __future__ import annotations

from opencontext_core.compat import StrEnum


class NodeKind(StrEnum):
    """All node types in the unified graph.

    The original unified-graph kinds (code/memory/harness/trace) are kept as-is.
    PR-008 KG v2 (OC-KG-001 §6) appends the architecture-book ``KgNodeType``
    kinds additively — every value below is a NEW string that never collides with
    or renames a previously persisted kind, so a legacy reader stays valid and
    ``models.kg_v2.KgNodeType`` (an alias of this enum) carries the full set.
    """

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

    # --- KG v2 (OC-KG-001 §6), append-only -------------------------------------
    # Code/file topology
    DIRECTORY = "directory"
    PACKAGE = "package"
    MODULE = "module"
    SYMBOL = "symbol"
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"

    # Project surface
    COMMAND = "command"
    PLUGIN = "plugin"

    # Organization graph
    OWNER = "owner"
    TEAM = "team"

    # Knowledge / governance
    DECISION = "decision"
    CONSTRAINT = "constraint"

    # Runtime entities
    SESSION = "session"
    RUN = "run"
    ARTIFACT = "artifact"

    # Registries
    SKILL = "skill"
    PERSONA = "persona"
    HARNESS = "harness"
    WORKFLOW = "workflow"
    CAPABILITY = "capability"

    # Observability
    RECEIPT = "receipt"
    EVENT = "event"

    # Engineering / SDD domain (mirrors the indexing-side extension)
    REQUIREMENT = "requirement"
    TASK = "task"
    PHASE = "phase"

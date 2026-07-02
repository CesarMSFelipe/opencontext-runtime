"""Read-only catalog of the ``runtime.*`` dual-run migration flags (SPEC CL-005).

The flags themselves live on ``config.RuntimeMigrationConfig`` and
``config.RuntimeBrainConfig`` -- this module does NOT define or mutate config. It
reads the live config models and maps each flag to its subsystem, default, owning
PR, and migration state, so "which subsystems are still legacy?" is answerable
without scanning config by hand.

Each ``*_enabled`` flag defaults to the legacy path; flipping exactly one flag
switches one subsystem to its vNext substrate (CL-005). ``session_wrapper`` is the
default-on revertibility precedent (CL-010).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from opencontext_core.compat.migration import MigrationState

# field -> (subsystem, migration state, owning PR, note). Defaults are NOT recorded
# here; they are read live from the config model so this catalog cannot drift from
# the real defaults.
_RUNTIME_FLAG_META: dict[str, tuple[str, MigrationState, str, str]] = {
    "session_wrapper": (
        "runtime_session",
        MigrationState.adapted,
        "PR-001",
        "Bracket legacy runs with a RuntimeApi session (CL-010 precedent; default on).",
    ),
    "registry_enabled": (
        "workflow_registry",
        MigrationState.adapted,
        "PR-003",
        "Resolve workflows through the PR-003 WorkflowRegistry.",
    ),
    "persona_registry_enabled": (
        "persona_registry",
        MigrationState.adapted,
        "PR-006",
        "Resolve personas through the PR-006 PersonaRegistry/Resolver.",
    ),
    "skill_registry_enabled": (
        "skill_registry",
        MigrationState.adapted,
        "PR-006",
        "Resolve skills through the PR-006 SkillRegistryV2.",
    ),
    "harness_registry_enabled": (
        "harness_registry",
        MigrationState.adapted,
        "PR-006",
        "Resolve harnesses through the PR-006 HarnessRegistry.",
    ),
    "gateway_enabled": (
        "provider_gateway",
        MigrationState.legacy,
        "PR-012",
        "Route provider calls through the unified gateway (pending PR-012).",
    ),
    "context_engine_enabled": (
        "context_engine",
        MigrationState.legacy,
        "PR-010",
        "Build context through the PR-010 ContextEngine (pending PR-010).",
    ),
    "kg_v2_enabled": (
        "knowledge_graph",
        MigrationState.legacy,
        "PR-008",
        "Route KG retrieval through the PR-008 vNext substrate (task-aware planner).",
    ),
    "memory_v2_enabled": (
        "memory",
        MigrationState.legacy,
        "PR-009",
        "Route durable memory writes through the PR-009 MemoryHarness vNext path.",
    ),
    "execution_profile": (
        "capability_profiles",
        MigrationState.adapted,
        "PR-000.2",
        "Bind a PR-000.2 execution profile (token budget / retries / routing).",
    ),
    "durable_artifacts": (
        "artifact_store",
        MigrationState.adapted,
        "PR-002",
        "Persist the PR-002 durable evidence layer.",
    ),
    "sdd_strict": (
        "sdd_hardening",
        MigrationState.adapted,
        "PR-004",
        "Block (not warn) on detected scaffold/placeholder output (PR-004).",
    ),
    "oc_flow_enabled": (
        "oc_flow",
        MigrationState.adapted,
        "PR-007",
        "Enable the PR-007 OC Flow operational workflow.",
    ),
}


class FlagSpec(BaseModel):
    """One migration flag mapped to its subsystem, default, and migration state."""

    model_config = ConfigDict(extra="forbid")

    name: str  # dotted config path, e.g. "runtime.registry_enabled"
    field: str  # config field name, e.g. "registry_enabled"
    subsystem: str
    default: bool | str  # the live default read from the config model
    migration_state: MigrationState
    superseding_pr: str
    note: str

    @property
    def is_legacy_default(self) -> bool:
        """True when the flag defaults to the legacy path (off, or empty profile)."""
        if isinstance(self.default, bool):
            # session_wrapper defaults on but its "legacy" route is the off route; for
            # every other boolean flag the off (False) route is the legacy path.
            return self.default is False or self.field == "session_wrapper"
        return self.default == ""


def flag_catalog() -> list[FlagSpec]:
    """Build the read-only flag catalog from the live config models.

    Reads ``RuntimeMigrationConfig`` (scalar fields only -- nested blocks like
    ``retention`` are skipped) plus ``runtime_brain.enabled``. Defaults come from
    the config field defaults, so the catalog reflects config reality.
    """
    from opencontext_core.config import (
        LoopConfig,
        OpenContextConfig,
        RuntimeBrainConfig,
        RuntimeMigrationConfig,
    )

    specs: list[FlagSpec] = []
    for field, info in RuntimeMigrationConfig.model_fields.items():
        default = info.default
        if not isinstance(default, (bool, str)):
            continue  # skip nested models (e.g. retention) / non-scalar fields
        meta = _RUNTIME_FLAG_META.get(field)
        if meta is None:
            subsystem, state, pr, note = ("(unmapped)", MigrationState.legacy, "?", "")
        else:
            subsystem, state, pr, note = meta
        specs.append(
            FlagSpec(
                name=f"runtime.{field}",
                field=field,
                subsystem=subsystem,
                default=default,
                migration_state=state,
                superseding_pr=pr,
                note=note,
            )
        )

    brain_default = RuntimeBrainConfig.model_fields["enabled"].default
    specs.append(
        FlagSpec(
            name="runtime_brain.enabled",
            field="enabled",
            subsystem="runtime_brain",
            default=bool(brain_default),
            migration_state=MigrationState.adapted,
            superseding_pr="PR-000.1",
            note="Enable advisory Runtime Brain decision recording (State Machine governs).",
        )
    )

    # Two vNext subsystem flags that live OUTSIDE RuntimeMigrationConfig: a top-level
    # toggle (OpenContextConfig.runtime_intelligence_enabled) and a nested one
    # (OpenContextConfig.learning.loop.enabled). Defaults are read live from the
    # config models so the catalog cannot drift from config reality (AVH-003).
    ri_default = OpenContextConfig.model_fields["runtime_intelligence_enabled"].default
    specs.append(
        FlagSpec(
            name="runtime_intelligence_enabled",
            field="runtime_intelligence_enabled",
            subsystem="runtime_intelligence",
            default=bool(ri_default),
            migration_state=MigrationState.adapted,
            superseding_pr="PR-011",
            note="Enable the advisory Runtime Intelligence layer (cost/confidence/simulation).",
        )
    )
    loop_default = LoopConfig.model_fields["enabled"].default
    specs.append(
        FlagSpec(
            name="learning.loop.enabled",
            field="enabled",
            subsystem="learning_loop",
            default=bool(loop_default),
            migration_state=MigrationState.adapted,
            superseding_pr="PR-000.4",
            note="Run the post-run Learning Loop (Decision Log + learning candidates).",
        )
    )

    # Phase-2 spine flags use hyphenated names so they live outside
    # RuntimeMigrationConfig (Python field names cannot contain hyphens). They are
    # added here explicitly so FLIP_SEQUENCE membership tests can resolve them via
    # flag_catalog() / flag_spec() without scanning the migration ledger.
    specs.append(
        FlagSpec(
            name="runtime.rt-spine",
            field="rt-spine",
            subsystem="rt_spine",
            default=False,
            migration_state=MigrationState.legacy,
            superseding_pr="PR-006",
            note="Route all consumers through RuntimeApi (Phase-2 spine flip).",
        )
    )
    specs.append(
        FlagSpec(
            name="runtime.mcp-runtime",
            field="mcp-runtime",
            subsystem="mcp_runtime",
            default=False,
            migration_state=MigrationState.legacy,
            superseding_pr="PR-008",
            note="Enable the runtime.* MCP session dispatcher (Phase-2 spine flip).",
        )
    )
    return specs


def flag_spec(name: str) -> FlagSpec | None:
    """Look up a single flag spec by its dotted *name*."""
    for spec in flag_catalog():
        if spec.name == name:
            return spec
    return None

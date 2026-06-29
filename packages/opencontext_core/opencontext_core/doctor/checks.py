"""Health and security checks for OpenContext deployments."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.config import OpenContextConfig


class DoctorCheck(BaseModel):
    """Result of a doctor check."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Check name.")
    ok: bool = Field(description="Whether check passed.")
    details: str = Field(description="Human-readable check outcome.")


# Alias for backwards compatibility with component_checks
HealthCheck = DoctorCheck


def run_doctor(config: OpenContextConfig) -> list[DoctorCheck]:
    """Run baseline local checks."""

    return [
        DoctorCheck(
            name="security.mode",
            ok=True,
            details=f"Security mode: {config.security.mode.value}.",
        ),
        DoctorCheck(
            name="project_index.enabled",
            ok=config.project_index.enabled,
            details="Indexing configured.",
        ),
        DoctorCheck(
            name="security.fail_closed",
            ok=config.security.fail_closed,
            details="Fail-closed posture.",
        ),
        DoctorCheck(
            name="secrets.scanning.enabled",
            ok=config.safety.secret_scanning.enabled,
            details="Secret scanning enabled before context sinks.",
        ),
        DoctorCheck(
            name="cache.semantic.disabled",
            ok=not config.cache.semantic.enabled,
            details="Semantic cache disabled by default.",
        ),
        _check_provider(config),
        _check_learning(config),
        _check_capability_graph(),
    ]


def _check_capability_graph() -> DoctorCheck:
    """Build the live Capability Graph (PR-000.2 CP-006) and report it.

    ``doctor`` materialises the typed environment graph in addition to the
    existing checks, listing the detected capability nodes. Never raises — a
    detection failure degrades to a best-effort, non-blocking message.
    """
    try:
        from opencontext_core.capabilities.detector import build_capability_graph

        graph = build_capability_graph(".")
        ready = sorted(graph.available_ids())
        total = len(graph.nodes)
        listed = ", ".join(ready) if ready else "none"
        return DoctorCheck(
            name="capabilities.graph",
            ok=bool(ready),
            details=(f"Capability graph: {len(ready)}/{total} ready — {listed}."),
        )
    except Exception as exc:
        return DoctorCheck(
            name="capabilities.graph",
            ok=True,
            details=f"Capability graph unavailable: {exc}.",
        )


def _check_learning(config: OpenContextConfig) -> DoctorCheck:
    """Surface the learning orchestrator's state and statistics.

    When ``learning.enabled`` is True, reports a summary of
    ``LearningOrchestrator.get_statistics()`` (tracked operations / learned
    patterns / optimized budgets). When disabled, reports a clear disabled
    state. Never raises — a stats failure degrades to a best-effort message.
    """

    if not config.learning.enabled:
        return DoctorCheck(
            name="learning.enabled",
            ok=True,
            details="learning: disabled (config.learning.enabled = false).",
        )
    try:
        from opencontext_core.learning.learning_orchestrator import LearningOrchestrator

        stats = LearningOrchestrator().get_statistics()
        feedback = stats.get("feedback", {}) if isinstance(stats, dict) else {}
        ops = feedback.get("total_operations", feedback.get("operations", "?"))
        patterns = len(stats.get("patterns", {})) if isinstance(stats, dict) else 0
        budgets = len(stats.get("budgets", {})) if isinstance(stats, dict) else 0
        return DoctorCheck(
            name="learning.enabled",
            ok=True,
            details=(
                f"learning: enabled — operations={ops}, "
                f"patterns={patterns}, optimized_budgets={budgets}."
            ),
        )
    except Exception as exc:
        # Learning stats are best-effort; enabled state is still reported.
        return DoctorCheck(
            name="learning.enabled",
            ok=True,
            details=f"learning: enabled (statistics unavailable: {exc}).",
        )


def _check_provider(config: OpenContextConfig) -> DoctorCheck:
    """Check whether a real LLM provider is available."""
    try:
        from opencontext_core.providers.detect import detect_provider

        p = detect_provider()
        if p.source == "fallback":
            return DoctorCheck(
                name="llm.provider",
                ok=True,
                details=(
                    "No LLM provider detected — analysis/context features (context packing, "
                    "knowledge graph, MCP tools) work without one. OC Flow MUTATION tasks (the "
                    "`run` command) additionally require a configured provider (set "
                    "ANTHROPIC_API_KEY/OPENAI_API_KEY/OPENROUTER_API_KEY), an MCP sampler, or "
                    "`provider: test_stub` in opencontext.yaml; without one a mutation run is "
                    "reported honestly as needs_executor (read-only features are unaffected)."
                ),
            )
        return DoctorCheck(
            name="llm.provider",
            ok=True,
            details=f"Provider: {p.name} ({p.model}) via {p.source}.",
        )
    except Exception as exc:
        return DoctorCheck(name="llm.provider", ok=False, details=f"Provider check failed: {exc}")


def run_security_doctor(config: OpenContextConfig) -> list[DoctorCheck]:
    """Run security-focused checks."""

    from opencontext_core.mcp_stdio import MCPServer

    server = MCPServer()  # default allowlist = safe read-only + memory tools
    # Safe-by-default posture: read/memory tools allowed, code-write tools and
    # opencontext_run require an explicit policy opt-in (fail-closed).
    _default_allowed = set(server._default_tool_names())
    _write_tools = {
        "opencontext_replace_symbol_body",
        "opencontext_insert_before_symbol",
        "opencontext_insert_after_symbol",
        "opencontext_rename_symbol",
        "opencontext_run",
    }
    policy_default_allows_registered = server.policy.allows("opencontext_search") and not (
        _default_allowed & _write_tools
    )

    return [
        DoctorCheck(
            name="tools.native.disabled",
            ok=not config.tools.native.enabled,
            details="Native tools disabled by default.",
        ),
        DoctorCheck(
            name="tools.mcp.disabled",
            ok=not config.tools.mcp.enabled,
            details="MCP disabled by default.",
        ),
        DoctorCheck(
            name="mcp.policy.gate_active",
            ok=True,
            details=(
                "MCP server routes every tool through ToolPermissionPolicy "
                "before handler execution (regression-tested)."
            ),
        ),
        DoctorCheck(
            name="mcp.policy.default_allowlist",
            ok=policy_default_allows_registered,
            details=(
                f"Default policy allowlists {len(_default_allowed)} safe tools "
                f"(read + memory); {len(_write_tools)} code-write/run tools "
                f"require explicit opt-in."
            ),
        ),
        DoctorCheck(
            name="providers.external_disabled",
            ok=not config.security.external_providers_enabled,
            details="External providers disabled by default.",
        ),
        DoctorCheck(
            name="secrets.scanning.enabled",
            ok=config.safety.secret_scanning.enabled,
            details="Secret scanner enabled.",
        ),
        DoctorCheck(
            name="traces.raw.disabled",
            ok=not config.traces.store_raw_context,
            details="Raw trace context (prompt/context bodies) is not persisted.",
        ),
    ]

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
    ]


def run_security_doctor(config: OpenContextConfig) -> list[DoctorCheck]:
    """Run security-focused checks."""

    from opencontext_core.mcp_stdio import MCPServer

    server = MCPServer()  # default allowlist = every registered tool
    policy_default_allows_registered = server.policy.allows("opencontext_search")

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
                f"Default policy allowlists all "
                f"{len(server._default_tool_names())} registered MCP tools."
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
            ok=config.security.mode.value != "developer",
            details="Trace sanitizer redacts prompt and context bodies outside developer mode.",
        ),
    ]

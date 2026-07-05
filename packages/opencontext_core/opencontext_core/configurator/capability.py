"""Client capability matrix (Workstream L).

A structured, honest statement of what each known agent client supports —
so the product never implies uniform support. Built from the live adapter
declarations, not a hand-maintained table that can drift.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from opencontext_core.configurator.adapter import iter_adapters

InstructionsScope = Literal["project", "home"]

RecommendedFlow = Literal[
    "native_oc_new",
    "mcp_run",
    "cli_loop",
    "instructions_only",
]


class ClientCapability(BaseModel):
    """What one agent client supports."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    mcp: bool = Field(description="Whether OpenContext can wire MCP for this client.")
    mcp_shape: str = Field(description="MCP config wire shape (json/toml/yaml variant).")
    honors_agents_md: bool = Field(description="Whether the client reads AGENTS.md.")
    instructions_scope: InstructionsScope = Field(
        description="Where the instructions file lives: project root or client home."
    )
    instructions_filename: str = Field(description="The instructions filename written for it.")

    supports_slash_commands: bool = False
    supports_subagents: bool = False
    supports_task_tool: bool = False
    supports_sampling: bool = False
    supports_streaming_status: bool = False
    supports_tool_approvals: bool = False
    supports_hooks: bool = False

    recommended_flow: RecommendedFlow = "instructions_only"


class CapabilityMatrix(BaseModel):
    """The full client capability matrix."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.capability_matrix.v1"
    clients: list[ClientCapability] = Field(default_factory=list)

    def get(self, agent_id: str) -> ClientCapability | None:
        return next((c for c in self.clients if c.agent_id == agent_id), None)


_FLOW_CAPS: dict[str, dict[str, object]] = {
    "claude-code": {
        "supports_slash_commands": True,
        "supports_subagents": True,
        "supports_task_tool": True,
        "supports_sampling": False,
        "supports_streaming_status": True,
        "supports_tool_approvals": True,
        "supports_hooks": True,
        "recommended_flow": "native_oc_new",
    },
    "opencode": {
        "supports_slash_commands": False,
        "supports_subagents": True,
        "supports_task_tool": False,
        # Not advertised at MCP initialize as of opencode 1.17.12; capability
        # detection auto-upgrades to the sampling path if a future version
        # advertises it.
        "supports_sampling": False,
        "supports_streaming_status": True,
        "supports_tool_approvals": True,
        "supports_hooks": False,
        "recommended_flow": "mcp_run",
    },
    "cursor": {
        "supports_slash_commands": False,
        "supports_subagents": False,
        "supports_task_tool": False,
        "supports_sampling": False,
        "supports_streaming_status": False,
        "supports_tool_approvals": False,
        "supports_hooks": False,
        "recommended_flow": "mcp_run",
    },
    "codex": {
        "supports_slash_commands": False,
        "supports_subagents": False,
        "supports_task_tool": False,
        "supports_sampling": False,
        "supports_streaming_status": False,
        "supports_tool_approvals": False,
        "supports_hooks": False,
        "recommended_flow": "cli_loop",
    },
    "aider": {
        "supports_slash_commands": False,
        "supports_subagents": False,
        "supports_task_tool": False,
        "supports_sampling": False,
        "supports_streaming_status": False,
        "supports_tool_approvals": False,
        "supports_hooks": False,
        "recommended_flow": "instructions_only",
    },
}


def build_capability_matrix() -> CapabilityMatrix:
    """Build the capability matrix from the live adapter declarations."""
    clients: list[ClientCapability] = []
    for adapter in iter_adapters():
        extra = _FLOW_CAPS.get(adapter.agent_id, {})
        clients.append(
            ClientCapability(
                agent_id=adapter.agent_id,
                mcp=True,
                mcp_shape=adapter.mcp_shape.value,
                honors_agents_md=adapter.honors_agents_md,
                instructions_scope=("project" if adapter.instructions_project_scoped else "home"),
                instructions_filename=adapter.instructions_filename,
                **extra,  # type: ignore[arg-type]
            )
        )
    return CapabilityMatrix(clients=clients)

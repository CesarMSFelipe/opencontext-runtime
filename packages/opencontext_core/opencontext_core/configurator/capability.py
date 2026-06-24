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


class CapabilityMatrix(BaseModel):
    """The full client capability matrix."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "opencontext.capability_matrix.v1"
    clients: list[ClientCapability] = Field(default_factory=list)

    def get(self, agent_id: str) -> ClientCapability | None:
        return next((c for c in self.clients if c.agent_id == agent_id), None)


def build_capability_matrix() -> CapabilityMatrix:
    """Build the capability matrix from the live adapter declarations."""
    clients: list[ClientCapability] = []
    for adapter in iter_adapters():
        clients.append(
            ClientCapability(
                agent_id=adapter.agent_id,
                # Every known MCP shape is an MCP-capable wire format.
                mcp=True,
                mcp_shape=adapter.mcp_shape.value,
                honors_agents_md=adapter.honors_agents_md,
                instructions_scope=(
                    "project" if adapter.instructions_project_scoped else "home"
                ),
                instructions_filename=adapter.instructions_filename,
            )
        )
    return CapabilityMatrix(clients=clients)

"""Tests for the client capability matrix (Workstream L)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.configurator.adapter import KNOWN_AGENTS
from opencontext_core.configurator.capability import (
    CapabilityMatrix,
    ClientCapability,
    build_capability_matrix,
)


def test_matrix_schema_version() -> None:
    assert build_capability_matrix().schema_version == "opencontext.capability_matrix.v1"


def test_matrix_covers_all_known_agents() -> None:
    matrix = build_capability_matrix()
    ids = {c.agent_id for c in matrix.clients}
    assert ids == set(KNOWN_AGENTS)


def test_get_returns_client() -> None:
    matrix = build_capability_matrix()
    c = matrix.get("claude-code")
    assert c is not None
    assert c.agent_id == "claude-code"
    assert c.mcp is True
    assert c.instructions_scope in ("project", "home")


def test_get_unknown_returns_none() -> None:
    assert build_capability_matrix().get("not-a-real-client") is None


def test_every_client_has_an_mcp_shape() -> None:
    for c in build_capability_matrix().clients:
        assert c.mcp_shape
        assert c.instructions_filename


def test_matrix_round_trip() -> None:
    matrix = build_capability_matrix()
    restored = CapabilityMatrix.model_validate(matrix.model_dump())
    assert len(restored.clients) == len(matrix.clients)


def test_client_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        ClientCapability(
            agent_id="x",
            mcp=True,
            mcp_shape="json_servers",
            honors_agents_md=True,
            instructions_scope="project",
            instructions_filename="AGENTS.md",
            bogus=1,
        )


def test_instructions_scope_is_constrained() -> None:
    with pytest.raises(ValidationError):
        ClientCapability(
            agent_id="x",
            mcp=True,
            mcp_shape="json_servers",
            honors_agents_md=True,
            instructions_scope="elsewhere",  # not project|home
            instructions_filename="AGENTS.md",
        )

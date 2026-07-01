"""Tests for skills.v2.persona — tool compatibility enforcement."""

from __future__ import annotations

import pytest

from opencontext_core.skills.v2.persona import Persona, ToolNotAllowedError


def test_unknown_tool_raises() -> None:
    """Persona rejects tools not in its allowed set."""
    p = Persona(name="senior-architect", allowed_tools=("read", "grep"))
    with pytest.raises(ToolNotAllowedError):
        p.check_tool("bash")
    # allowed tool passes
    p.check_tool("read")

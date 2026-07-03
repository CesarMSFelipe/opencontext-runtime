"""Tests for context.v2.budget — unified ResourceBudget (CONV2)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opencontext_core.context.v2.budget import ResourceBudget


def _valid() -> ResourceBudget:
    return ResourceBudget(
        token_limit=3000,
        time_limit_ms=5000,
        tool_calls=10,
        parallel_nodes=4,
        memory_bytes=64 * 1024 * 1024,
        cost_units=1.5,
    )


def test_validates_all_six_fields() -> None:
    # missing any of the six → ValidationError
    with pytest.raises(ValidationError):
        ResourceBudget()  # type: ignore[call-arg]

    for missing in (
        "token_limit",
        "time_limit_ms",
        "tool_calls",
        "parallel_nodes",
        "memory_bytes",
        "cost_units",
    ):
        data = _valid().model_dump()
        data.pop(missing)
        with pytest.raises(ValidationError):
            ResourceBudget.model_validate(data)


def test_negative_values_rejected() -> None:
    data = _valid().model_dump()
    data["token_limit"] = -1
    with pytest.raises(ValidationError):
        ResourceBudget.model_validate(data)


def test_token_limit_serializes_to_int() -> None:
    b = _valid()
    assert b.token_limit == 3000
    assert b.time_limit_ms == 5000


def test_runtime_api_exposes_resource_budget() -> None:
    """RuntimeApi re-exports ResourceBudget for unified callers (commit-010 redirect)."""
    from opencontext_core.runtime import api as runtime_api

    assert getattr(runtime_api, "ResourceBudget", None) is ResourceBudget

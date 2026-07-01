"""Tests for skills.v2.outputs — output format validation."""

from __future__ import annotations

import pytest

from opencontext_core.skills.v2.outputs import (
    OutputContract,
    OutputFormat,
    validate_output_format,
)


def test_format_yaml_rejected() -> None:
    """YAML is not a valid output format — only json/markdown/text are accepted."""
    with pytest.raises(ValueError):
        OutputFormat("yaml")
    # json / markdown / text are accepted
    assert OutputFormat("json").value == "json"
    assert OutputFormat("markdown").value == "markdown"


def test_validate_output_format_rejects_yaml() -> None:
    """validate_output_format raises when the contract declares yaml."""
    contract = OutputContract(name="decision", format="yaml")
    with pytest.raises(ValueError):
        validate_output_format(contract)

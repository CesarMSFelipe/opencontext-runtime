"""Unit tests for opencontext_core.errors exception hierarchy."""

from __future__ import annotations

import pytest

from opencontext_core.errors import (
    ConfigurationError,
    IndexingError,
    LLMGatewayError,
    MemoryStoreError,
    OpenContextError,
    ProviderError,
    WorkflowExecutionError,
)

_ALL_ERRORS = [
    ConfigurationError,
    IndexingError,
    MemoryStoreError,
    WorkflowExecutionError,
    LLMGatewayError,
    ProviderError,
]


def test_base_hierarchy() -> None:
    """All custom errors must inherit from OpenContextError."""
    for cls in _ALL_ERRORS:
        assert issubclass(cls, OpenContextError), (
            f"{cls.__name__} is not a subclass of OpenContextError"
        )


def test_provider_error_inherits_llm_gateway() -> None:
    """ProviderError must be a subclass of LLMGatewayError."""
    assert issubclass(ProviderError, LLMGatewayError)


def test_errors_carry_messages() -> None:
    """Raising an error with a message preserves the message in str(exc)."""
    with pytest.raises(ConfigurationError) as exc_info:
        raise ConfigurationError("bad config value")
    assert "bad config value" in str(exc_info.value)


def test_all_errors_instantiable_without_args() -> None:
    """All error classes can be instantiated without arguments."""
    for cls in _ALL_ERRORS:
        exc = cls()
        assert isinstance(exc, OpenContextError)

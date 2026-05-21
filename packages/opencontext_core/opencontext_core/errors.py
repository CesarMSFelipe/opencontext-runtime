"""Domain-specific exceptions for OpenContext Runtime."""


class OpenContextError(Exception):
    """Base exception for all OpenContext Runtime errors."""


class ConfigurationError(OpenContextError):
    """Raised when runtime configuration is invalid or incomplete."""


class IndexingError(OpenContextError):
    """Raised when project indexing cannot complete."""


class MemoryStoreError(OpenContextError):
    """Raised when project memory cannot be read or written."""


class WorkflowExecutionError(OpenContextError):
    """Raised when a configured workflow cannot be executed."""


class LLMGatewayError(OpenContextError):
    """Raised when an LLM gateway cannot complete a request."""


class ProviderError(LLMGatewayError):
    """Raised when a provider adapter fails."""

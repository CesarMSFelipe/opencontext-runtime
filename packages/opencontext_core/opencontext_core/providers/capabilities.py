"""Provider capability model (book §25 "Capability Model"; PR-012).

Each provider advertises a static capability set so routing can *require* a
capability (e.g. ``vision``) and pick a provider that advertises it, instead of
hardcoding a vendor. The table is static — deterministic, offline-safe, and
testable; vendors rarely change capability classes. An unknown provider
advertises the empty set.
"""

from __future__ import annotations

from opencontext_core.compat import StrEnum


class ProviderCapability(StrEnum):
    """A capability a provider may advertise (book §25)."""

    STRUCTURED_OUTPUT = "structured_output"
    TOOL_USE = "tool_use"
    LONG_CONTEXT = "long_context"
    REASONING = "reasoning"
    STREAMING = "streaming"
    VISION = "vision"
    EMBEDDINGS = "embeddings"


_C = ProviderCapability

# Static per-provider advertisement; an absent provider -> empty set.
_PROVIDER_CAPS: dict[str, frozenset[ProviderCapability]] = {
    "anthropic": frozenset(
        {_C.STRUCTURED_OUTPUT, _C.TOOL_USE, _C.LONG_CONTEXT, _C.REASONING, _C.VISION}
    ),
    "openai": frozenset(
        {
            _C.STRUCTURED_OUTPUT,
            _C.TOOL_USE,
            _C.LONG_CONTEXT,
            _C.REASONING,
            _C.VISION,
            _C.EMBEDDINGS,
        }
    ),
    "openrouter": frozenset({_C.STRUCTURED_OUTPUT, _C.TOOL_USE, _C.LONG_CONTEXT}),
    "ollama": frozenset({_C.TOOL_USE, _C.LONG_CONTEXT, _C.EMBEDDINGS}),
    "local": frozenset({_C.LONG_CONTEXT}),
    "mock": frozenset(),
}


def capabilities_for(provider: str) -> frozenset[ProviderCapability]:
    """Return the capability set a *provider* advertises (empty if unknown)."""

    return _PROVIDER_CAPS.get(provider, frozenset())


def supports(provider: str, required: frozenset[ProviderCapability]) -> bool:
    """Return whether *provider* advertises every capability in *required*."""

    return required <= capabilities_for(provider)


def providers_with(required: frozenset[ProviderCapability]) -> list[str]:
    """Return the providers (table order) advertising every capability in *required*."""

    return [name for name, caps in _PROVIDER_CAPS.items() if required <= caps]

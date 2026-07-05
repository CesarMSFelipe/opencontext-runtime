"""PR-012 ProviderAdapter Protocol — structural typing."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from opencontext_core.providers.v2.spec import ProviderSpec


@runtime_checkable
class ProviderAdapter(Protocol):
    """Minimum surface every provider adapter must expose.

    Structural typing: any object with ``spec()`` and ``call(prompt, **kwargs)``
    satisfies this Protocol. Concrete implementations live outside ``opencontext_core``
    (provider SDKs are forbidden in core per REPO_GUIDELINES).
    """

    def spec(self) -> ProviderSpec: ...

    def call(self, prompt: str, **kwargs: Any) -> str: ...

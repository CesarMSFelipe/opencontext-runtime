"""Provider-response cache (cache type 5 — ``provider_response``).

Caches provider responses **locally**, keyed on
``(provider, model, prompt_version, normalized_input_hash, context_hash)``. It is
provider-neutral: it makes no external cache-API calls. Reuse of external
explicit-cache APIs (Anthropic/OpenAI) is delegated to PR-012 (Provider Gateway);
this module is the local seam that gateway plugs into.

It reuses the existing KV-prefix stabilization (``compression/cache_aligner.py``
``CacheAligner``) to compute the stable ``prefix_hash`` / cache hint rather than
re-implementing prompt ordering.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import Field

from opencontext_core.cache.base import CacheEntry, CacheProvenance, CacheType, _hash_text
from opencontext_core.cache.store import CcrBackedCacheStore
from opencontext_core.compression.cache_aligner import CacheAligner


class ProviderCacheEntry(CacheEntry):
    """Typed entry for a locally cached provider response."""

    cache_type: CacheType = CacheType.provider_response
    provider: str = Field(description="Provider identifier.")
    model: str = Field(description="Model name.")
    prefix_hash: str | None = Field(
        default=None, description="Stable KV-prefix hash from CacheAligner."
    )


class ProviderResponseCache:
    """Local, provider-neutral response cache (PR-012 gateway seam)."""

    def __init__(
        self,
        store: CcrBackedCacheStore,
        *,
        enabled: bool = False,
        aligner: CacheAligner | None = None,
    ) -> None:
        self._store = store
        self.enabled = enabled
        self._aligner = aligner

    @staticmethod
    def _key(
        provider: str,
        model: str,
        prompt_version: str,
        input_hash: str,
        context_hash: str,
    ) -> str:
        parts = ("prov", provider, model, prompt_version, input_hash, context_hash)
        return _hash_text("::".join(parts))

    def _prefix_hash(self, system_prompt: str | None, context: str) -> str | None:
        if self._aligner is None or system_prompt is None:
            return None
        return self._aligner.align(system_prompt, context).prefix_hash

    def get(
        self,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        user_input: str,
        context: str,
    ) -> str | None:
        """Return a cached response or ``None`` on a miss."""

        if not self.enabled:
            return None
        key = self._key(
            provider, model, prompt_version, _hash_text(user_input), _hash_text(context)
        )
        return self._store.get_value_typed(key, str(CacheType.provider_response))

    def put(
        self,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        user_input: str,
        context: str,
        response: str,
        system_prompt: str | None = None,
        provenance: CacheProvenance | None = None,
        classification: str = "internal",
    ) -> None:
        """Store a provider response locally (provider-neutral)."""

        if not self.enabled:
            return
        key = self._key(
            provider, model, prompt_version, _hash_text(user_input), _hash_text(context)
        )
        entry = ProviderCacheEntry(
            key=key,
            value_ref=_hash_text(response),
            provider=provider,
            model=model,
            prefix_hash=self._prefix_hash(system_prompt, context),
            provenance=provenance or CacheProvenance(content_hash=_hash_text(response)),
            classification=classification,
        )
        self._store.put(entry, response)

    def get_or_produce(
        self,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        user_input: str,
        context: str,
        produce: Callable[[], str],
        system_prompt: str | None = None,
        provenance: CacheProvenance | None = None,
        classification: str = "internal",
    ) -> tuple[str, bool]:
        """Return ``(response, was_hit)``; ``produce`` (the provider call) is skipped on a hit."""

        cached = self.get(
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            user_input=user_input,
            context=context,
        )
        if cached is not None:
            return cached, True
        response = produce()
        self.put(
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            user_input=user_input,
            context=context,
            response=response,
            system_prompt=system_prompt,
            provenance=provenance,
            classification=classification,
        )
        return response, False

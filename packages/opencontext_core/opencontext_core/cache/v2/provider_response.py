"""Cache v2 — `ProviderCacheEntry` keyed by `hash(spec + payload)`."""

from __future__ import annotations

import hashlib
import json

from opencontext_core.cache.base import CacheEntry, CacheType


def provider_key(spec: dict[str, object], payload: dict[str, object]) -> str:
    """Deterministic key from provider spec + request payload."""
    blob = json.dumps(
        {"payload": payload, "spec": spec},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _fingerprint(d: dict[str, object]) -> str:
    blob = json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class ProviderCacheEntry(CacheEntry):
    """Provider-response cache entry keyed by spec + payload fingerprints."""

    cache_type: CacheType = CacheType.provider_response
    provider: str = ""
    model_name: str = ""
    spec_fingerprint: str = ""
    payload_hash: str = ""

    @classmethod
    def build(
        cls,
        *,
        spec: dict[str, object],
        payload: dict[str, object],
        value_ref: str,
        provider: str = "",
        model_name: str = "",
    ) -> ProviderCacheEntry:
        return cls(
            key=provider_key(spec, payload),
            value_ref=value_ref,
            provider=provider,
            model_name=model_name,
            spec_fingerprint=_fingerprint(spec),
            payload_hash=_fingerprint(payload),
        )


__all__ = ["ProviderCacheEntry", "provider_key"]

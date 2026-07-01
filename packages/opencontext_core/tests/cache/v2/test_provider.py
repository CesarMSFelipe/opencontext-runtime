"""REQ-cache-v2-001 — ProviderCacheEntry round-trip."""

from __future__ import annotations


class TestProviderCache:
    def test_round_trip_with_spec_and_payload(self) -> None:
        from opencontext_core.cache.v2.provider_response import (
            ProviderCacheEntry,
            provider_key,
        )

        spec = {"model": "mock-llm", "temperature": 0.0}
        payload = {"messages": [{"role": "user", "content": "hi"}]}
        k1 = provider_key(spec, payload)
        k2 = provider_key(spec, payload)
        assert k1 == k2

        e = ProviderCacheEntry(
            key=k1,
            value_ref="v_ref_1",
            provider="mock",
            model_name="mock-llm",
            spec_fingerprint="spec_hash",
            payload_hash="payload_hash",
        )
        assert e.provider == "mock"
        assert e.model_name == "mock-llm"
        # model_dump -> re-parse round trip
        from opencontext_core.cache.v2.provider_response import ProviderCacheEntry as PCE

        rebuilt = PCE.model_validate(e.model_dump())
        assert rebuilt.value_ref == "v_ref_1"
        assert rebuilt.provider == "mock"

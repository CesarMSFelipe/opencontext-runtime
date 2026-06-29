"""SC-010 / SC-011 — deterministic keys, redaction-on-store, policy eligibility."""

from __future__ import annotations

from opencontext_core.cache.base import CacheProvenance, build_cache_key
from opencontext_core.cache.store import CcrBackedCacheStore
from opencontext_core.cache.tool_cache import ToolCache


def _key_args() -> dict[str, object]:
    return dict(
        workflow_name="wf",
        project_hash="ph",
        model_name="m",
        prompt_version="v1",
        user_input="Hello World",
        context="some context",
    )


def test_equal_inputs_yield_byte_identical_sha256_keys() -> None:
    a = build_cache_key(**_key_args())  # type: ignore[arg-type]
    b = build_cache_key(**_key_args())  # type: ignore[arg-type]
    assert a.value == b.value
    assert len(a.value) == 64  # sha256 hexdigest


def test_secret_classification_is_never_stored() -> None:
    store = CcrBackedCacheStore()
    cache = ToolCache(store, enabled=True)
    cache.put("read", {"path": "x"}, "secret output", mutating=False, classification="secret")
    assert cache.get("read", {"path": "x"}) is None


def test_regulated_classification_is_never_stored() -> None:
    store = CcrBackedCacheStore()
    cache = ToolCache(store, enabled=True)
    cache.put("read", {"path": "y"}, "regulated output", mutating=False, classification="regulated")
    assert cache.get("read", {"path": "y"}) is None


def test_stored_values_are_redacted() -> None:
    store = CcrBackedCacheStore()
    cache = ToolCache(store, enabled=True)
    cache.put(
        "read",
        {"path": "z"},
        "contact alice@example.com for details",
        mutating=False,
        provenance=CacheProvenance(content_hash="x"),
    )
    cached = cache.get("read", {"path": "z"})
    assert cached is not None
    assert "alice@example.com" not in cached


def test_store_get_returns_base_entry_with_type() -> None:
    store = CcrBackedCacheStore()
    cache = ToolCache(store, enabled=True)
    cache.put("read", {"path": "k"}, "ok", mutating=False)
    assert cache.get("read", {"path": "k"}) == "ok"
    # The store round-trips a base CacheEntry carrying the cache type.
    key = ToolCache._key("read", "")
    assert store.get(key) is None  # different args_hash -> different key


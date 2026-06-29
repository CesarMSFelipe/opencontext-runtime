"""SC-001 — unified typed cache entry layer."""

from __future__ import annotations

from opencontext_core.cache.ast_cache import AstCacheEntry
from opencontext_core.cache.base import CacheEntry, CacheType
from opencontext_core.cache.provider_cache import ProviderCacheEntry
from opencontext_core.cache.semantic_cache import SemanticCacheEntry
from opencontext_core.cache.tool_cache import ToolCacheEntry


def test_cache_type_has_exactly_seven_members() -> None:
    assert {t.value for t in CacheType} == {
        "semantic",
        "prompt_context",
        "tool_output",
        "ast",
        "provider_response",
        "kg_query",
        "memory_retrieval",
    }
    assert len(list(CacheType)) == 7


def test_four_named_entries_subclass_cache_entry() -> None:
    for cls in (SemanticCacheEntry, ToolCacheEntry, AstCacheEntry, ProviderCacheEntry):
        assert issubclass(cls, CacheEntry)


def test_schema_version_string_matches() -> None:
    entry = CacheEntry(cache_type=CacheType.kg_query, key="abc")
    assert entry.schema_version == "opencontext.cache_entry.v1"


def test_each_typed_entry_carries_its_cache_type() -> None:
    assert ToolCacheEntry(tool_name="t", args_hash="h").cache_type == CacheType.tool_output
    assert AstCacheEntry(path="a.py").cache_type == CacheType.ast
    assert ProviderCacheEntry(provider="p", model="m").cache_type == CacheType.provider_response


def test_entry_id_is_content_addressed() -> None:
    entry = CacheEntry(cache_type=CacheType.ast, key="deadbeef")
    assert entry.entry_id.startswith("cache_")

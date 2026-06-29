"""SC-004 — tool-output cache (read-only only)."""

from __future__ import annotations

from opencontext_core.cache.store import CcrBackedCacheStore
from opencontext_core.cache.tool_cache import ToolCache


def test_read_only_identical_call_hits() -> None:
    store = CcrBackedCacheStore()
    cache = ToolCache(store, enabled=True)
    calls = {"n": 0}

    def run_tool() -> str:
        calls["n"] += 1
        return "tool output"

    out1, hit1 = cache.get_or_produce("grep", {"q": "x"}, run_tool, mutating=False)
    out2, hit2 = cache.get_or_produce("grep", {"q": "x"}, run_tool, mutating=False)

    assert out1 == out2 == "tool output"
    assert hit1 is False
    assert hit2 is True
    assert calls["n"] == 1  # tool invoked once


def test_mutating_tool_is_never_cached() -> None:
    store = CcrBackedCacheStore()
    cache = ToolCache(store, enabled=True)
    cache.put("write_file", {"path": "x"}, "done", mutating=True)
    assert cache.get("write_file", {"path": "x"}) is None


def test_different_args_miss() -> None:
    store = CcrBackedCacheStore()
    cache = ToolCache(store, enabled=True)
    cache.put("grep", {"q": "a"}, "out-a", mutating=False)
    assert cache.get("grep", {"q": "a"}) == "out-a"
    assert cache.get("grep", {"q": "b"}) is None

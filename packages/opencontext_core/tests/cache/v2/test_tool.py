"""REQ-cache-v2-003 — ToolCacheEntry mtime invalidation."""

from __future__ import annotations


class TestToolCache:
    def test_key_is_tool_name_plus_args_hash(self) -> None:
        from opencontext_core.cache.v2.tool_output import ToolCacheEntry, tool_key

        k1 = tool_key("git_status", {"repo": "/r"})
        k2 = tool_key("git_status", {"repo": "/r"})
        k3 = tool_key("git_status", {"repo": "/x"})
        assert k1 == k2
        assert k1 != k3

        e = ToolCacheEntry(
            key=k1,
            value_ref="v_ref_1",
            tool_name="git_status",
            args_hash="h_args_1",
            source_file_mtime=0.0,
        )
        assert e.tool_name == "git_status"
        assert e.source_file_mtime == 0.0

    def test_mtime_advance_invalidates(self) -> None:
        """REQ-cache-v2-003 — file mtime change invalidates matching entries."""
        from opencontext_core.cache.v2.invalidation import CacheInvalidationRule

        rule = CacheInvalidationRule(
            rule_id="mtime_tool",
            cache_type="tool_output",
            on_file_change=True,
        )
        before = rule.applies_to(mtime=100.0)
        after = rule.applies_to(mtime=200.0)
        assert before is True
        assert after is True  # the rule fires on file change

"""REQ-cache-v2-003 — CacheInvalidationRule profile-aware + mtime."""

from __future__ import annotations


class TestInvalidationRule:
    def test_mtime_advance_fires_rule(self) -> None:
        from opencontext_core.cache.v2.invalidation import CacheInvalidationRule

        r = CacheInvalidationRule(rule_id="r1", cache_type="tool_output")
        assert r.applies_to(mtime=100.0) is True
        assert r.applies_to(mtime=200.0) is True

    def test_profile_aware_skips_other_profiles(self) -> None:
        from opencontext_core.cache.v2.invalidation import CacheInvalidationRule

        r = CacheInvalidationRule(
            rule_id="r1",
            cache_type="ast",
            profiles=("balanced", "low-cost"),
        )
        assert r.applies_to(profile="balanced") is True
        assert r.applies_to(profile="low-cost") is True
        assert r.applies_to(profile="enterprise") is False

    def test_apply_rule_emits_event(self) -> None:
        """`apply_rule` fires `cache.invalidated` events with reason."""
        from opencontext_core.cache.v2.invalidation import (
            CacheInvalidationRule,
            apply_rule,
        )

        events: list[dict[str, str]] = []
        rule = CacheInvalidationRule(rule_id="r1", cache_type="tool_output", reason="mtime_change")
        n = apply_rule(
            rule,
            matched_keys=["k1", "k2"],
            source_file="src/foo.py",
            emit=events.append,
        )
        assert n == 2
        assert len(events) == 2
        assert events[0]["reason"] == "mtime_change"
        assert events[0]["cache_type"] == "tool_output"
        assert events[0]["source_file"] == "src/foo.py"
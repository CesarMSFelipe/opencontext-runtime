"""REQ-cache-v2-003 — AstCacheEntry file_hash + symbol_path key."""

from __future__ import annotations


class TestAstCache:
    def test_key_file_hash_plus_symbol_path(self) -> None:
        from opencontext_core.cache.v2.ast import AstCacheEntry, ast_key

        k1 = ast_key("src/foo.py", "Foo.bar")
        k2 = ast_key("src/foo.py", "Foo.bar")
        k3 = ast_key("src/foo.py", "Foo.baz")
        k4 = ast_key("src/bar.py", "Foo.bar")
        assert k1 == k2
        assert k1 != k3  # symbol path matters
        assert k1 != k4  # file matters

        e = AstCacheEntry(
            key=k1,
            value_ref="v_ref_1",
            file_path="src/foo.py",
            file_hash="h_xyz",
            symbol_path="Foo.bar",
        )
        assert e.file_hash == "h_xyz"
        assert e.symbol_path == "Foo.bar"

    def test_file_hash_invalidation(self) -> None:
        """REQ-cache-v2-003 — file_hash change invalidates the entry."""
        from opencontext_core.cache.v2.ast import is_file_hash_match
        from opencontext_core.cache.v2.invalidation import CacheInvalidationRule

        rule = CacheInvalidationRule(
            rule_id="ast_hash",
            cache_type="ast",
            on_file_change=True,
        )
        # rule recognizes file-hash fingerprint
        assert rule.cache_type == "ast"
        assert is_file_hash_match("h_xyz", "h_xyz") is True
        assert is_file_hash_match("h_xyz", "h_abc") is False

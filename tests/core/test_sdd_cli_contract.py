"""SDD CLI contract tests — verify deprecated SDD commands are properly removed."""

from __future__ import annotations

from opencontext_cli.main import _DeprecationAwareParser


class TestSddDeprecation:
    def test_sdd_is_in_deprecated_set(self) -> None:
        """The 'sdd' top-level command is in the _DEPRECATED frozenset."""
        assert "sdd" in _DeprecationAwareParser._DEPRECATED

    def test_deprecated_set_covers_v1_removals(self) -> None:
        """All v1.0 removed commands are in the _DEPRECATED frozenset."""
        expected = {"sdd", "check", "packs", "cost", "policy", "drupal", "ddev"}
        assert expected.issubset(_DeprecationAwareParser._DEPRECATED)

    def test_original_deprecated_commands_still_present(self) -> None:
        """Legacy deprecated commands are still in the frozenset."""
        original = {"run", "orchestrate", "validate", "propose", "governance", "evidence"}
        assert original.issubset(_DeprecationAwareParser._DEPRECATED)

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
        """Legacy deprecated commands are still in the frozenset.

        NOTE: ``run`` was removed from this set by PR-007 — it is now the OC Flow
        execution command (`opencontext run "<task>" --workflow oc-flow`, FLOW-16),
        no longer a deprecated alias.
        """
        original = {"orchestrate", "validate", "propose", "governance", "evidence"}
        assert original.issubset(_DeprecationAwareParser._DEPRECATED)

    def test_run_is_no_longer_deprecated(self) -> None:
        """PR-007 FLOW-16: ``run`` is the OC Flow execution command, not deprecated."""
        assert "run" not in _DeprecationAwareParser._DEPRECATED

"""SDD CLI contract tests — verify SDD is a live command, not deprecated."""

from __future__ import annotations

from opencontext_cli.main import _DeprecationAwareParser


class TestSddDeprecation:
    def test_sdd_is_not_in_deprecated_set(self) -> None:
        """'sdd' is a live subcommand (restored in r13/r14) — must NOT be in _DEPRECATED.

        Keeping 'sdd' in _DEPRECATED would cause argparse errors on valid sdd sub-flags
        (e.g. --json) to print "'sdd' has been removed." instead of the real error.
        """
        assert "sdd" not in _DeprecationAwareParser._DEPRECATED

    def test_deprecated_set_covers_v1_removals(self) -> None:
        """All v1.0 removed commands (excluding 'sdd', which is live) are in _DEPRECATED."""
        # 'sdd' was removed from this set in r13/r14 — it is now a live registered
        # subcommand (see add_sdd_parser() in main.py).
        expected = {"check", "packs", "cost", "policy", "drupal", "ddev"}
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

    def test_sdd_is_live_registered_subcommand(self) -> None:
        """'sdd' is accessible as a live subcommand via add_sdd_parser() (r13/r14)."""
        import argparse

        from opencontext_cli.commands.sdd_cmd import add_sdd_parser

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        add_sdd_parser(sub)
        args = parser.parse_args(["sdd", "status"])
        assert args.command == "sdd"

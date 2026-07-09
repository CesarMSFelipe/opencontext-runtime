"""Anti-drift: `opencontext maturity` and the --help policy read the SAME table.

Two maturity tables exist and are intentionally different:

- ``contracts/command_registry.py`` (17 stable) — the CANONICAL Sprint 2 truth
  layer. ``main._apply_maturity_help_policy`` reads it to decide the ``(preview)``
  suffix in ``opencontext --help``.
- ``command_maturity.py`` (wider, 49 stable) — the OLDER visibility map, kept
  only for its completeness test.

The bug: ``opencontext maturity commands`` imported the OLD map, so it reported
``mcp``/``verify``/``session`` as ``stable`` while ``--help`` marked the very
same commands ``(preview)`` — contradictory user-facing signals.

This test does NOT assert the two dicts are equal (they are intentionally
different). It asserts the two CONSUMERS agree: for the previously-divergent
commands, the maturity the ``maturity`` command reports equals the maturity the
--help policy uses. It fails if the command ever reads a different table again.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

# The commands that diverged between the two tables before the fix. Each is
# "preview" in the canonical registry and was "stable" in the legacy map.
DIVERGENT_COMMANDS = ("mcp", "verify", "session")


def _maturity_command_levels() -> dict[str, str]:
    """The per-command levels emitted by `opencontext maturity commands`."""
    from opencontext_cli.commands.maturity_cmd import _commands_report

    report = _commands_report()
    return dict(report["commands"])


def test_maturity_command_agrees_with_help_policy_on_divergent_commands() -> None:
    from opencontext_cli.contracts.command_registry import maturity

    command_levels = _maturity_command_levels()

    for command in DIVERGENT_COMMANDS:
        help_level = maturity(command)
        reported_level = command_levels[command]
        assert reported_level == help_level, (
            f"`opencontext maturity` reports {command!r} as {reported_level!r} "
            f"but the --help policy uses {help_level!r}; the maturity command must "
            f"read the canonical contracts.command_registry table, not a different one."
        )
        # Both should be preview per the canonical product contract.
        assert reported_level == "preview"


def test_maturity_command_reads_canonical_registry_not_legacy_map() -> None:
    """The command's data source is byte-for-byte the canonical registry."""
    from opencontext_cli.contracts.command_registry import COMMAND_MATURITY as CANONICAL

    assert _maturity_command_levels() == dict(CANONICAL)


def test_maturity_commands_json_reflects_canonical_stable_count() -> None:
    """End-to-end: the JSON output carries the 17-stable canonical contract."""
    import contextlib
    import io

    from opencontext_cli.commands.maturity_cmd import handle_maturity
    from opencontext_cli.contracts.command_registry import COMMAND_MATURITY as CANONICAL

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        handle_maturity(SimpleNamespace(maturity_command="commands", json=True, output=None))
    data = json.loads(buffer.getvalue().strip())

    canonical_stable = sorted(c for c, lvl in CANONICAL.items() if lvl == "stable")
    assert data["by_level"]["stable"] == canonical_stable
    assert data["counts"]["stable"] == len(canonical_stable)
    # The divergent commands must NOT appear in the stable list.
    for command in DIVERGENT_COMMANDS:
        assert command not in data["by_level"]["stable"]

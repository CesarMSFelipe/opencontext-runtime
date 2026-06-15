"""Smoke tests for mutation CLI commands."""

import argparse
from unittest.mock import MagicMock, patch


def test_import_handle_mutation():
    """Import handle_mutation without crash."""
    from opencontext_cli.commands.mutation_cmd import add_mutation_commands, handle_mutation

    assert callable(handle_mutation)
    assert callable(add_mutation_commands)


def test_mutation_run_returns_0_when_unavailable(capsys):
    """_handle_mutation_run returns 0 when framework not available (not crash)."""
    from opencontext_cli.commands.mutation_cmd import _handle_mutation_run

    args = argparse.Namespace(root=".", scope="changed", threshold=80)

    # MutationRunner.run returns a result with available=False
    mock_result = MagicMock()
    mock_result.available = False
    mock_result.error = "No mutation framework installed"

    with patch("opencontext_core.mutation.runner.MutationRunner") as MockRunner:
        MockRunner.return_value.run.return_value = mock_result
        result = _handle_mutation_run(args)

    assert result == 0


def test_handle_mutation_no_subcommand_returns_1(capsys):
    """handle_mutation with no subcommand prints usage and returns 1."""
    from opencontext_cli.commands.mutation_cmd import handle_mutation

    args = argparse.Namespace(mutation_cmd=None)
    result = handle_mutation(args)
    assert result == 1


def test_add_mutation_commands_registers_parser():
    """add_mutation_commands registers the mutation subparser."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    from opencontext_cli.commands.mutation_cmd import add_mutation_commands

    add_mutation_commands(subparsers)
    parsed = parser.parse_args(["mutation", "run", "--threshold", "90"])
    assert parsed.threshold == 90

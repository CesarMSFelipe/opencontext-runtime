"""Smoke tests for contract CLI commands."""

import argparse


def test_import_handle_contract():
    """Import handle_contract without crash."""
    from opencontext_cli.commands.contract_cmd import add_contract_commands, handle_contract

    assert callable(handle_contract)
    assert callable(add_contract_commands)


def test_contract_build_returns_int():
    """_handle_contract_build returns 0 or 1 (not crash)."""
    from opencontext_cli.commands.contract_cmd import _handle_contract_build

    args = argparse.Namespace(query="fix bug in user service", output="yaml", root=".")
    result = _handle_contract_build(args)
    assert result in (0, 1)


def test_handle_contract_no_subcommand_returns_1(capsys):
    """handle_contract with no subcommand prints usage and returns 1."""
    from opencontext_cli.commands.contract_cmd import handle_contract

    args = argparse.Namespace(contract_cmd=None)
    result = handle_contract(args)
    assert result == 1


def test_add_contract_commands_registers_parser():
    """add_contract_commands registers the contract subparser."""
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    from opencontext_cli.commands.contract_cmd import add_contract_commands

    add_contract_commands(subparsers)
    parsed = parser.parse_args(["contract", "build", "--query", "test task"])
    assert parsed.query == "test task"

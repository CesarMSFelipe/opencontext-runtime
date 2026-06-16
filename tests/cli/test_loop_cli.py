"""Tests for the loop CLI command."""


def test_loop_dry_run_exits_zero():
    import argparse

    from opencontext_cli.commands.loop_cmd import handle_loop

    args = argparse.Namespace(
        task="fix bug",
        flow="quick",
        compress="efficient",
        root=".",
        max_rounds=1,
        autonomous=False,
        dry_run=True,
    )
    assert handle_loop(args) == 0


def test_loop_flows_defined():
    from opencontext_cli.commands.loop_cmd import FLOWS

    assert "quick" in FLOWS
    assert "autonomous" in FLOWS
    assert "full" in FLOWS

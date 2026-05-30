"""Agent hints CLI commands."""

from __future__ import annotations

import json
from typing import Any

from opencontext_core.dx.agent_hints import AgentHintsManager
from opencontext_core.dx.console_styles import console


def add_hints_parser(subparsers: Any) -> None:
    """Add hints command parsers."""
    import argparse

    hints_parser = subparsers.add_parser("hints", help=argparse.SUPPRESS)
    hints_sub = hints_parser.add_subparsers(dest="hints_command", required=True)
    hints_sub.add_parser("init", help="Initialize .opencontexthints file.")
    hints_sub.add_parser("show", help="Show combined hints.")
    hints_sub.add_parser("validate", help="Validate hints files.")


def handle_hints(args: Any) -> None:
    """Handle hints commands."""
    command = args.hints_command
    json_output = getattr(args, "json", False)

    manager = AgentHintsManager()

    if command == "init":
        path = manager.init_hints_file()
        if path:
            console.success(f"Created {path}")
            console.info("Edit the file to add your project conventions")
        else:
            console.warning(".opencontexthints already exists")
    elif command == "show":
        hints = manager.get_all_hints()
        if hints:
            ctx = manager.to_context_string(hints)
            if json_output:
                print(json.dumps({"hints": ctx}, indent=2))
            else:
                console.header("Agent Hints")
                console.panel(ctx, title=hints.project_name or "Project Hints")
        else:
            console.warning("No hints found. Run 'opencontext hints init' to create them.")
    elif command == "validate":
        files = manager.discover_hints()
        valid: list[str] = []
        invalid: list[str] = []
        for f in files:
            parsed = manager.parse_hints_file(f)
            if parsed:
                valid.append(str(f))
            else:
                invalid.append(str(f))
        if json_output:
            print(json.dumps({"valid": valid, "invalid": invalid, "total": len(files)}, indent=2))
        else:
            console.header("Hints Validation")
            console.success(f"Valid: {len(valid)}")
            if invalid:
                console.error(f"Invalid: {len(invalid)}")
                for item in invalid:
                    console.print(f"  [dim]✗ {item}[/]")
            console.info(f"Total files checked: {len(files)}")
    else:
        console.error(f"Unknown hints command: {command}")

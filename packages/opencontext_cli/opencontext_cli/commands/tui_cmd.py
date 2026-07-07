"""tui — launch the OpenContext terminal UI (Textual).

``opencontext tui [root]`` opens the full-screen home dashboard on the
resolved workspace root. ``--smoke`` boots the app headless through Textual's
test runner (no TTY required), presses ``q`` and exits 0 — the CI-safe boot
check. Outside a workspace the command prints a readable error and exits 3
(``ExitCode.CONFIG_INVALID``); a smoke run still boots to the error screen.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from opencontext_cli.contracts.exit_codes import ExitCode


def add_tui_parser(subparsers: Any) -> None:
    """Add the top-level ``tui`` command."""
    tui_parser = subparsers.add_parser(
        "tui",
        help="Launch the OpenContext terminal UI.",
        description=(
            "Open the full-screen terminal UI (dashboard, runs, SDD workspace, "
            "doctor, config inspector, uninstall preview) for a workspace."
        ),
    )
    tui_parser.add_argument("root", nargs="?", default=None, help="Workspace root (default: cwd).")
    tui_parser.add_argument(
        "--smoke",
        action="store_true",
        help="Headless boot check: mount the app, press q, exit 0 (CI-safe, no TTY).",
    )


def handle_tui(args: Any) -> int:
    """Launch the TUI (or run the headless smoke check). Returns the exit code."""
    from opencontext_cli.output import eprint
    from opencontext_core.config import find_config

    root = Path(getattr(args, "root", None) or ".").expanduser().resolve()
    smoke = bool(getattr(args, "smoke", False))

    if not root.is_dir():
        if smoke:
            return _smoke_boot("error", root)
        eprint(f"Workspace root does not exist: {root}")
        return int(ExitCode.CONFIG_INVALID)

    workspace_config = find_config(root)
    os.chdir(root)  # every screen resolves project state relative to cwd

    if smoke:
        return _smoke_boot("home" if workspace_config else "error", root)

    if workspace_config is None:
        eprint(f"No OpenContext workspace found at {root} (no opencontext.yaml here or above).")
        eprint(
            "Run 'opencontext init' to create one, or open another root: opencontext tui <path>."
        )
        return int(ExitCode.CONFIG_INVALID)

    # CFG-004: the effective interface settings gate TUI launch. The ci profile
    # (interface.tui=false) refuses the full-screen UI with a readable error;
    # --smoke stays available above as the CI-safe headless boot check.
    from opencontext_core.config_resolver import resolve_interface

    interface = resolve_interface(root)
    if not interface.tui:
        eprint("The TUI is disabled by the active configuration profile (interface.tui=false).")
        eprint(
            "Select an interactive profile (e.g. 'profile: local' in opencontext.yaml) "
            "or use the equivalent CLI commands instead."
        )
        return int(ExitCode.CONFIG_INVALID)

    from opencontext_cli.tui import run_home_tui

    if not run_home_tui():
        eprint("opencontext tui needs an interactive terminal (use --smoke for a headless check).")
        return int(ExitCode.FAILURE)
    return int(ExitCode.OK)


def _smoke_boot(start: str, root: Path) -> int:
    """Boot the app headless via the Textual test runner, press q, exit clean."""
    import asyncio

    from opencontext_cli.tui.app import OpenContextApp

    async def scenario() -> None:
        app = OpenContextApp(start=start, root=root)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(scenario())
    print(f"tui smoke: booted the '{start}' screen headless and quit cleanly.")
    return int(ExitCode.OK)

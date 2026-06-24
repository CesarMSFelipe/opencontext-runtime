"""OpenContext unified Textual TUI.

One TUI system for every interactive surface — same logo, same palette, same
navigation, same animations. Screens are registered on a single ``OpenContextApp``
so a command just opens the app at the right screen instead of inventing its own
menu. See ``brand`` for the shared chrome and ``app`` for the application shell.
"""

from opencontext_cli.tui.app import run_cockpit_tui, run_config_tui, run_home_tui

__all__ = ["run_cockpit_tui", "run_config_tui", "run_home_tui"]

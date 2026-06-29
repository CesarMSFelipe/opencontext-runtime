"""Built-in workflow templates shipped with OpenContext."""

from __future__ import annotations

from pathlib import Path


def builtins_dir() -> Path:
    """Return the directory holding the built-in workflow YAML templates."""
    return Path(__file__).resolve().parent

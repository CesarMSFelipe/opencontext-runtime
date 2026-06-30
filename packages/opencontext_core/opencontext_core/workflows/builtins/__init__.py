"""Built-in workflow templates shipped with OpenContext."""

from __future__ import annotations

from importlib.resources import files
from typing import Any


def builtins_dir() -> Any:
    """Return the directory holding the built-in workflow YAML templates."""
    return files(__package__)

"""Built-in skill definition templates shipped with OpenContext (PR-006)."""

from __future__ import annotations

from importlib.resources import files
from typing import Any


def builtins_dir() -> Any:
    """Return the directory holding the built-in skill definition YAML files."""
    return files(__package__)

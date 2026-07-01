"""Commit-009: TUI start action stub branches on rt-spine flag.

A minimal :func:`tui_action.start_session` stub that returns the routing
identity (``"spine"`` or ``"legacy"``) so the TUI can pick its path.
The full 12-screen TUI lands in commit-013.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from opencontext_core.compat import is_migrated_flag


def _import_action() -> Any:
    """Lazy import to avoid touching the stub unless the test needs it."""
    from opencontext_core.studio import tui_action

    return tui_action


def test_tui_uses_spine_when_on(tmp_path: Path) -> None:
    """When rt-spine is on, start_session returns ``\"spine\"``."""
    tui_action = _import_action()
    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        result = tui_action.start_session(task="do x", root=tmp_path, profile="balanced")
    assert result == "spine"


def test_tui_uses_legacy_when_off(tmp_path: Path) -> None:
    """When rt-spine is off, start_session returns ``\"legacy\"``."""
    tui_action = _import_action()
    # Default: flag is off (legacy path).
    assert is_migrated_flag("rt-spine") is False
    result = tui_action.start_session(task="do x", root=tmp_path, profile="balanced")
    assert result == "legacy"


def test_tui_start_session_forwards_args(tmp_path: Path) -> None:
    """The TUI start action accepts task/root/profile kwargs (commit-009 shape)."""
    tui_action = _import_action()
    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        result = tui_action.start_session(
            task="build feature", root=tmp_path, profile="careful"
        )
    assert result == "spine"  # the kwargs are accepted without TypeError


def test_tui_start_session_default_profile(tmp_path: Path) -> None:
    """``profile`` defaults to ``\"balanced\"`` when not supplied."""
    tui_action = _import_action()
    with patch("opencontext_core.compat.is_migrated_flag", return_value=True):
        # Only task + root supplied -- no TypeError, default profile used.
        result = tui_action.start_session(task="x", root=tmp_path)
    assert result == "spine"
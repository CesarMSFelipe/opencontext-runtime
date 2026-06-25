"""GraphScreen must be openable by mode/root/run_id, not only a prebuilt view_state.

Validation report 16.3: the natural UX is GraphScreen(mode=..., root=..., run_id=...).
Previously the constructor only accepted view_state and raised TypeError on `mode`.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_cli.tui.graph.models import GraphMode
from opencontext_cli.tui.screens.graph import GraphScreen


def test_graphscreen_kg_mode_constructs(tmp_path: Path) -> None:
    """KG mode with an empty project loads an empty (non-crashing) view."""
    screen = GraphScreen(mode=GraphMode.KG, root=tmp_path)
    assert screen._view_state.mode == GraphMode.KG


def test_graphscreen_run_mode_constructs(tmp_path: Path) -> None:
    """RUN mode with an unknown run_id falls back to an empty RUN view."""
    screen = GraphScreen(mode=GraphMode.RUN, run_id="does-not-exist", root=tmp_path)
    assert screen._view_state.mode == GraphMode.RUN
    assert screen._view_state.nodes == []


def test_graphscreen_default_constructs() -> None:
    """No args still works (back-compat)."""
    screen = GraphScreen()
    assert screen._view_state is not None

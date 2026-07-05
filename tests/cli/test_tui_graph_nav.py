"""Keyboard navigation of the knowledge-graph explorer — drill in and back.

Driven headless through Textual's ``run_test`` pilot (wrapped in ``asyncio.run``
so no pytest-asyncio is needed). The neighbor loader is monkeypatched to a
deterministic fake, so this proves the navigation wiring without an indexed KG.
"""

from __future__ import annotations

import asyncio

import pytest

textual = pytest.importorskip("textual", reason="textual not installed")

from opencontext_cli.tui.graph.models import GraphMode  # noqa: E402
from opencontext_cli.tui.screens.graph import Neighbor  # noqa: E402


def _focus(nid: str) -> Neighbor:
    return Neighbor(nid, nid, "method", "")


def _nbrs(nid: str) -> list[Neighbor]:
    return [
        Neighbor(f"{nid}.a", f"{nid}_callee", "method", "calls"),
        Neighbor(f"{nid}.b", f"{nid}_caller", "function", "called by"),
    ]


def test_explorer_drill_and_back(monkeypatch: pytest.MonkeyPatch) -> None:
    from textual.app import App

    from opencontext_cli.tui.screens import graph as graph_mod
    from opencontext_cli.tui.screens.graph import GraphScreen

    monkeypatch.setattr(graph_mod, "pick_focus", lambda root=".": "root")
    monkeypatch.setattr(
        graph_mod, "load_node_neighbors", lambda nid, root=".": (_focus(nid), _nbrs(nid))
    )

    screen = GraphScreen(mode=GraphMode.KG, root=".")

    class _App(App):
        def on_mount(self) -> None:
            self.push_screen(screen)

    async def scenario() -> None:
        async with _App().run_test() as pilot:
            await pilot.pause()
            assert [n.node_id for n in screen._path] == ["root"]

            # Tab toggles between the List and Graph views (current view kept).
            assert screen._view.view == "list"
            await pilot.press("tab")
            await pilot.pause()
            assert screen._view.view == "graph"
            await pilot.press("tab")
            await pilot.pause()
            assert screen._view.view == "list"

            # Enter on the highlighted neighbor → drill one level deeper.
            await pilot.press("enter")
            await pilot.pause()
            assert len(screen._path) == 2

            # Drill again → two deep.
            await pilot.press("enter")
            await pilot.pause()
            assert len(screen._path) == 3

            # Backspace climbs back out one level at a time.
            await pilot.press("backspace")
            await pilot.pause()
            assert len(screen._path) == 2
            await pilot.press("backspace")
            await pilot.pause()
            assert [n.node_id for n in screen._path] == ["root"]

    asyncio.run(scenario())

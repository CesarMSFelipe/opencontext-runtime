"""E2E tests for D4: GraphScreen import, node cap, and non-TTY renderer fallback.

NOTE: Textual is an optional dependency. All tests that need the CLI TUI modules
load them via direct file path to avoid tui/__init__.py importing textual.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

# Base path for the CLI TUI modules.
_CLI_TUI_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "packages"
    / "opencontext_cli"
    / "opencontext_cli"
    / "tui"
)


def _load_from_file(name: str, filepath: Path) -> object:
    """Load a module from a file path without triggering package __init__."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(filepath))
    if spec is None:
        pytest.skip(f"Cannot find module at {filepath}")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except ImportError as exc:
        del sys.modules[name]
        pytest.skip(f"Import failed ({filepath.name}): {exc}")
    return mod


def _get_models():  # type: ignore[return]
    return _load_from_file(
        "opencontext_cli.tui.graph.models_test_isolated",
        _CLI_TUI_DIR / "graph" / "models.py",
    )


def _get_renderer():  # type: ignore[return]
    return _load_from_file(
        "opencontext_cli.tui.graph.renderer_test_isolated",
        _CLI_TUI_DIR / "graph" / "renderer.py",
    )


def _get_viewport():  # type: ignore[return]
    return _load_from_file(
        "opencontext_cli.tui.graph.viewport_test_isolated",
        _CLI_TUI_DIR / "graph" / "viewport.py",
    )


def _get_graph_screen():  # type: ignore[return]
    return _load_from_file(
        "opencontext_cli.tui.screens.graph_test_isolated",
        _CLI_TUI_DIR / "screens" / "graph.py",
    )


class TestGraphModulesExist:
    def test_models_py_exists(self) -> None:
        assert (_CLI_TUI_DIR / "graph" / "models.py").exists()

    def test_renderer_py_exists(self) -> None:
        assert (_CLI_TUI_DIR / "graph" / "renderer.py").exists()

    def test_viewport_py_exists(self) -> None:
        assert (_CLI_TUI_DIR / "graph" / "viewport.py").exists()

    def test_layout_py_exists(self) -> None:
        assert (_CLI_TUI_DIR / "graph" / "layout.py").exists()

    def test_graph_screen_py_exists(self) -> None:
        assert (_CLI_TUI_DIR / "screens" / "graph.py").exists()

    def test_graph_canvas_py_exists(self) -> None:
        assert (_CLI_TUI_DIR / "widgets" / "graph_canvas.py").exists()


class TestGraphViewStateCap:
    def test_over_cap_graph_trims_to_60(self) -> None:
        mod = _get_models()
        nodes = [mod.GraphNodeView(node_id=str(i), label=str(i)) for i in range(100)]
        state = mod.GraphViewState.build(nodes, [])
        assert len(state.nodes) <= 60

    def test_under_cap_graph_unchanged(self) -> None:
        mod = _get_models()
        nodes = [mod.GraphNodeView(node_id=str(i), label=str(i)) for i in range(10)]
        state = mod.GraphViewState.build(nodes, [])
        assert len(state.nodes) == 10

    def test_bfs_trims_from_focal_node(self) -> None:
        mod = _get_models()
        nodes = [mod.GraphNodeView(node_id=str(i), label=str(i)) for i in range(70)]
        edges = [mod.GraphEdgeView(source_id=str(i), target_id=str(i + 1)) for i in range(69)]
        state = mod.GraphViewState.build(nodes, edges, focal_node_id="0")
        assert len(state.nodes) <= 60

    def test_graph_mode_enum_has_required_values(self) -> None:
        mod = _get_models()
        assert mod.GraphMode.RUN == "run"
        assert mod.GraphMode.KG == "kg"
        assert mod.GraphMode.MEMORY == "memory"
        assert mod.GraphMode.CONTEXT == "context"
        assert mod.GraphMode.IMPACT == "impact"


class TestAsciiRendererFallback:
    def test_renderer_produces_non_empty_output(self) -> None:
        models = _get_models()
        renderer_mod = _get_renderer()

        nodes = [
            models.GraphNodeView(node_id="a", label="A", x=0.0, y=0.0),
            models.GraphNodeView(node_id="b", label="B", x=4.0, y=2.0),
        ]
        edges = [models.GraphEdgeView(source_id="a", target_id="b")]
        renderer = renderer_mod.AsciiGraphRenderer(width=40, height=12)
        output = renderer.render(nodes, edges, text_fallback=False)
        assert len(output) > 0

    def test_text_fallback_adjacency_list(self) -> None:
        models = _get_models()
        renderer_mod = _get_renderer()

        nodes = [
            models.GraphNodeView(node_id="alpha", label="Alpha"),
            models.GraphNodeView(node_id="beta", label="Beta"),
        ]
        edges = [models.GraphEdgeView(source_id="alpha", target_id="beta")]
        renderer = renderer_mod.AsciiGraphRenderer()
        output = renderer.render(nodes, edges, text_fallback=True)
        assert "Alpha" in output or "alpha" in output
        assert "->" in output or "adjacency" in output.lower()

    def test_empty_graph_returns_non_raising_output(self) -> None:
        renderer_mod = _get_renderer()
        renderer = renderer_mod.AsciiGraphRenderer()
        output = renderer.render([], [], text_fallback=True)
        assert isinstance(output, str)


class TestGraphViewport:
    def test_pan_updates_coordinates(self) -> None:
        mod = _get_viewport()
        vp = mod.GraphViewport()
        vp2 = vp.pan(3.0, -2.0)
        assert vp2.pan_x == pytest.approx(3.0)
        assert vp2.pan_y == pytest.approx(-2.0)

    def test_zoom_in_increases_scale(self) -> None:
        mod = _get_viewport()
        vp = mod.GraphViewport()
        original_zoom = vp.zoom
        vp2 = vp.zoom_in()
        assert vp2.zoom > original_zoom

    def test_zoom_out_decreases_scale(self) -> None:
        mod = _get_viewport()
        vp = mod.GraphViewport()
        original_zoom = vp.zoom
        vp2 = vp.zoom_out()
        assert vp2.zoom < original_zoom

    def test_zoom_out_clamped(self) -> None:
        mod = _get_viewport()
        vp = mod.GraphViewport()
        for _ in range(20):
            vp = vp.zoom_out()
        assert vp.zoom >= 0.1  # Must not go to zero.


class TestGraphScreenLoadFunctions:
    def test_load_graph_for_kg_empty_dir(self) -> None:
        # Empty project root → no KG DB → pick_focus returns None.
        # The interface evolved: graph.py exposes pick_focus/load_node_neighbors
        # rather than a load_graph_for_kg() aggregate. The new entry point
        # for "give me a focus to land on" is pick_focus(root).
        import tempfile

        mod = _get_graph_screen()
        with tempfile.TemporaryDirectory() as tmp:
            focus_id = mod.pick_focus(Path(tmp))
            assert focus_id is None

    def test_load_graph_for_run_missing_run(self) -> None:
        # No KG DB present → load_node_neighbors returns (None, []).
        # Missing run id cannot resolve to any node; the lookup must
        # degrade gracefully (no exception, empty neighbor list).
        import tempfile

        mod = _get_graph_screen()
        with tempfile.TemporaryDirectory() as tmp:
            focus, neighbors = mod.load_node_neighbors("nonexistent-run-id", root=Path(tmp))
            assert focus is None
            assert neighbors == []

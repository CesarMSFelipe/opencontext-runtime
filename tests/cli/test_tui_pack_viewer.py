"""CTX-008 tests: the TUI pack viewer renders context-pack.json fields and metrics.

DOC1 TUI-003 requires the pack viewer to show included files/symbols, included
memory, KG edges used, token estimates, and applied compression — plus the
mandatory ``context`` metrics block (KG_CONTEXT_COMPRESSION_CONTRACT).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

textual = pytest.importorskip("textual", reason="textual not installed")


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """An isolated OpenContext workspace: opencontext.yaml + private HOME/prefs."""
    from opencontext_core.user_prefs import UserConfigStore

    (tmp_path / "opencontext.yaml").write_text(
        "ui_language: en\nmemory:\n  provider: local\n", encoding="utf-8"
    )
    cfg_dir = tmp_path / ".config" / "opencontext"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", cfg_dir / "user-config.json")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _pack_result():
    """A realistic persisted pack: file symbol + memory item + compression + metrics."""
    from opencontext_core.context.packing import build_pack_metrics
    from opencontext_core.models.context import (
        CompressionPackMetadata,
        ContextItem,
        ContextOmission,
        ContextPackResult,
        ContextPriority,
    )

    graph_item = ContextItem(
        id="graph:src/auth.py:3:login",
        content="def login(username): ...",
        source="src/auth.py:3",
        source_type="graph_symbol",
        priority=ContextPriority.P1,
        tokens=40,
        score=0.9,
        metadata={
            "retrieval_source": "graph",
            "symbol_kind": "function",
            "graph_provenance": {
                "file_path": "src/auth.py",
                "line": 3,
                "relationships": ["calls:audit_login", "defined_in:src/auth.py"],
            },
        },
    )
    memory_item = ContextItem(
        id="memory:mem-auth-audit",
        content="AuthService.login must always call audit_login.",
        source="memory:auth:audit-decision",
        source_type="memory",
        priority=ContextPriority.P1,
        tokens=14,
        score=0.9,
        metadata={"retrieval_source": "memory"},
    )
    result = ContextPackResult(
        included=[graph_item, memory_item],
        omitted=[],
        used_tokens=54,
        available_tokens=2000,
        omissions=[
            ContextOmission(
                item_id="file:README.md", reason="token_budget_exceeded", tokens=500, score=0.1
            )
        ],
        compression=CompressionPackMetadata(
            enabled=True, tokens_before=100, tokens_after=54, items_compressed=1
        ),
    )
    return result.model_copy(update={"context": build_pack_metrics(result)})


def _write_run_pack(root: Path, run_id: str) -> Path:
    run_dir = root / ".opencontext" / "runs" / run_id
    run_dir.mkdir(parents=True)
    pack_path = run_dir / "context-pack.json"
    pack_path.write_text(_pack_result().model_dump_json(indent=2), encoding="utf-8")
    return pack_path


EXPECTED_FRAGMENTS = (
    "Included files/symbols",  # archivos/simbolos incluidos
    "src/auth.py:3",
    "Memory included",  # memoria incluida
    "memory:auth:audit-decision",
    "KG edges used",  # edges KG usados
    "calls:audit_login",
    "Tokens",  # tokens estimados
    "54",
    "2000",
    "Compression",  # compresion aplicada
    "memory_hits",  # metrics block
    "protected_spans",
    "excluded_files",
)


def test_render_pack_view_shows_tui_003_fields(workspace) -> None:
    """CTX-008: the pure pack renderer shows every TUI-003 field — included
    files/symbols, memory items, KG edges, token estimates, compression applied,
    and the mandatory metrics block."""
    from opencontext_cli.tui.screens.context import render_pack_view

    payload = json.loads(_pack_result().model_dump_json())
    text = render_pack_view(payload, pack_name="context-pack.json")

    for fragment in EXPECTED_FRAGMENTS:
        assert fragment in text, f"missing {fragment!r} in rendered pack view:\n{text}"


def test_context_viewer_screen_renders_pack_and_metrics(workspace) -> None:
    """CTX-008: TUI shows pack and metrics — the ContextViewerScreen renders the
    persisted run's context-pack.json fields (TUI-003) on screen via the pilot."""
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.context import ContextViewerScreen

    _write_run_pack(workspace, "run-ctx-008")
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(ContextViewerScreen())
            await pilot.pause()
            seen["text"] = str(app.screen.query_one("#context-content", Static).content)
            await pilot.press("escape")

    asyncio.run(scenario())
    for fragment in EXPECTED_FRAGMENTS:
        assert fragment in seen["text"], f"missing {fragment!r} on screen:\n{seen['text']}"


def test_context_pack_viewer_screen_renders_seeded_context(workspace) -> None:
    """TUI-SCREENS: the context pack viewer is a real, tested minimal screen —
    seeding a run with a context JSON and pushing ContextViewerScreen renders
    that pack (name + contents) on screen, not an empty or raw dump."""
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.context import ContextViewerScreen

    _write_run_pack(workspace, "run-tui-screens")
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(ContextViewerScreen())
            await pilot.pause()
            assert isinstance(app.screen, ContextViewerScreen)
            seen["text"] = str(app.screen.query_one("#context-content", Static).content)
            await pilot.press("escape")

    asyncio.run(scenario())
    assert "run-tui-screens" in seen["text"]  # the seeded run's pack was found
    assert "src/auth.py:3" in seen["text"]  # and its contents render


def test_pack_view_structures_all_six_required_facets(workspace) -> None:
    """TUI-FLOW-003: the pack view surfaces all six required facets as
    structured sections — included files, symbols, included memory, KG edges
    used, token estimate, and applied compression — independent of pack size."""
    from opencontext_cli.tui.screens.context import render_pack_view

    payload = json.loads(_pack_result().model_dump_json())
    text = render_pack_view(payload)

    # 1+2. included files/symbols (with symbol kind), 3. included memory
    assert "Included files/symbols" in text
    assert "[function]" in text
    assert "Memory included" in text
    # 4. KG edges used, 5. token estimate, 6. compression applied
    assert "KG edges used" in text
    assert "Tokens:" in text and "used 54 / budget 2000" in text
    assert "Compression:" in text and "applied" in text

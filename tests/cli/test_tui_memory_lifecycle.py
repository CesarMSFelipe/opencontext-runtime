"""Tests for MemoryBrowserScreen approval lifecycle (plan §5 TUI-005).

The browser lists v2 observations with their lifecycle state and lets the
user approve (``a``) or reject (``x``) the selected proposed memory through
the same ``mem_approve`` / ``mem_reject`` entry points the CLI verbs use.
Reject asks for confirmation via a modal; non-proposed rows are a no-op
with a status-bar hint.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

textual = pytest.importorskip("textual", reason="textual not installed")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _db_path(root: Path) -> Path:
    from opencontext_core.paths import StorageMode, resolve_storage_path

    return resolve_storage_path(root, StorageMode.local) / "memory_v2.db"


def _seed(
    root: Path,
    *,
    title: str,
    lifecycle_state: str,
    type: str = "mem_save",
    session_id: str = "s1",
    review_after: str | None = None,
    pinned: bool = False,
) -> int:
    """Write one observation into the workspace v2 store, returning its id."""
    from opencontext_memory import MemoryStore, Observation

    store = MemoryStore.open(_db_path(root))
    try:
        return store.write(
            Observation(
                session_id=session_id,
                title=title,
                content="body",
                type=type,
                lifecycle_state=lifecycle_state,
                review_after=review_after,
                pinned=pinned,
            )
        )
    finally:
        store.close()


def _row(root: Path, observation_id: int) -> sqlite3.Row:
    """The raw observation row (including soft-deleted rows)."""
    conn = sqlite3.connect(str(_db_path(root)))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT lifecycle_state, deleted_at FROM observations WHERE id = ?",
            (observation_id,),
        ).fetchone()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Unit tests — pure loader behind the screen
# ---------------------------------------------------------------------------


def test_list_memory_rows_shows_lifecycle_state(workspace) -> None:
    from opencontext_cli.tui.screens.memory import list_memory_rows

    _seed(workspace, title="Pending memory", lifecycle_state="proposed")
    rows = list_memory_rows(workspace)
    assert rows and rows[0]["title"] == "Pending memory"
    assert rows[0]["lifecycle_state"] == "proposed"


def test_list_memory_rows_empty_without_store(workspace) -> None:
    from opencontext_cli.tui.screens.memory import list_memory_rows

    assert list_memory_rows(workspace) == []
    assert not _db_path(workspace).is_file()  # listing must not create the db


# ---------------------------------------------------------------------------
# Pilot tests — lifecycle actions through the screen
# ---------------------------------------------------------------------------


def test_approve_flips_proposed_to_active(workspace) -> None:
    from textual.widgets import Label

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.memory import MemoryBrowserScreen

    obs_id = _seed(workspace, title="Pending memory", lifecycle_state="proposed")
    seen: dict[str, list[str]] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(MemoryBrowserScreen(root=workspace))
            await pilot.pause()
            seen["labels"] = [str(label.content) for label in app.screen.query(Label)]
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    assert any("proposed" in label for label in seen["labels"])
    row = _row(workspace, obs_id)
    assert row["lifecycle_state"] == "active"
    assert row["deleted_at"] is None


def test_reject_soft_deletes_after_confirmation(workspace) -> None:
    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.memory import (
        MemoryBrowserScreen,
        RejectConfirmScreen,
    )

    obs_id = _seed(workspace, title="Pending memory", lifecycle_state="proposed")

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(MemoryBrowserScreen(root=workspace))
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            assert isinstance(app.screen, RejectConfirmScreen)
            await pilot.press("y")
            await pilot.pause()
            assert isinstance(app.screen, MemoryBrowserScreen)
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    row = _row(workspace, obs_id)
    assert row["lifecycle_state"] == "rejected"
    assert row["deleted_at"] is not None


def test_reject_confirmation_can_be_cancelled(workspace) -> None:
    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.memory import (
        MemoryBrowserScreen,
        RejectConfirmScreen,
    )

    obs_id = _seed(workspace, title="Pending memory", lifecycle_state="proposed")

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(MemoryBrowserScreen(root=workspace))
            await pilot.pause()
            await pilot.press("x")
            await pilot.pause()
            assert isinstance(app.screen, RejectConfirmScreen)
            await pilot.press("n")
            await pilot.pause()
            assert isinstance(app.screen, MemoryBrowserScreen)
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    row = _row(workspace, obs_id)
    assert row["lifecycle_state"] == "proposed"
    assert row["deleted_at"] is None


def test_non_proposed_row_actions_are_noop_with_hint(workspace) -> None:
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.memory import MemoryBrowserScreen

    obs_id = _seed(workspace, title="Approved memory", lifecycle_state="active")
    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(MemoryBrowserScreen(root=workspace))
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            seen["approve_hint"] = str(app.screen.query_one("#memory-status", Static).content)
            await pilot.press("x")
            await pilot.pause()
            # No confirmation modal for a non-proposed row.
            assert isinstance(app.screen, MemoryBrowserScreen)
            seen["reject_hint"] = str(app.screen.query_one("#memory-status", Static).content)
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    assert "proposed" in seen["approve_hint"]
    assert "proposed" in seen["reject_hint"]
    row = _row(workspace, obs_id)
    assert row["lifecycle_state"] == "active"
    assert row["deleted_at"] is None


def test_empty_state_renders_without_store(workspace) -> None:
    from textual.widgets import Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.memory import MemoryBrowserScreen

    seen: dict[str, str] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(MemoryBrowserScreen(root=workspace))
            await pilot.pause()
            seen["empty"] = str(app.screen.query_one("#memory-empty", Static).content)
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    assert "No memories" in seen["empty"]


# ---------------------------------------------------------------------------
# TUI-FLOW-005 — type filter + trust/expiry/origin columns
# ---------------------------------------------------------------------------


def test_list_memory_rows_exposes_expiry_origin_and_type_filter(workspace) -> None:
    """TUI-FLOW-005: list_memory_rows exposes expiry (review_after) and origin
    (session_id/scope) per row, and filters by type when asked."""
    from opencontext_cli.tui.screens.memory import list_memory_rows

    _seed(
        workspace,
        title="Auth decision",
        lifecycle_state="active",
        type="decision",
        session_id="sess-auth",
        review_after="2099-01-01T00:00:00Z",
    )
    _seed(workspace, title="Plain note", lifecycle_state="proposed", type="mem_save")

    rows = list_memory_rows(workspace)
    assert len(rows) == 2
    decision = next(r for r in rows if r["type"] == "decision")
    assert decision["session_id"] == "sess-auth"
    assert decision["review_after"] == "2099-01-01T00:00:00Z"
    assert decision["scope"] == "project"

    filtered = list_memory_rows(workspace, type_filter="decision")
    assert [r["title"] for r in filtered] == ["Auth decision"]


def test_trust_label_derives_from_real_lifecycle_fields(workspace) -> None:
    """TUI-FLOW-005: the store tracks no numeric confidence — the viewer's
    trust label is honestly derived from real fields: pinned > proposed
    (unverified) > overdue review_after (needs_review) > trusted."""
    from opencontext_cli.tui.screens.memory import trust_label

    assert trust_label({"pinned": 1, "lifecycle_state": "active", "review_after": None}) == "pinned"
    assert (
        trust_label({"pinned": 0, "lifecycle_state": "proposed", "review_after": None})
        == "unverified"
    )
    assert (
        trust_label(
            {"pinned": 0, "lifecycle_state": "active", "review_after": "2000-01-01T00:00:00Z"}
        )
        == "needs_review"
    )
    assert (
        trust_label({"pinned": 0, "lifecycle_state": "active", "review_after": None}) == "trusted"
    )


def test_memory_screen_shows_trust_expiry_origin_columns(workspace) -> None:
    """TUI-FLOW-005: the memory viewer renders trust, expiry, and origin for
    each row alongside id/title/type/lifecycle state."""
    from textual.widgets import Label

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.memory import MemoryBrowserScreen

    _seed(
        workspace,
        title="Auth decision",
        lifecycle_state="active",
        type="decision",
        session_id="sess-auth",
        review_after="2099-01-01T00:00:00Z",
    )
    seen: dict[str, list[str]] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(MemoryBrowserScreen(root=workspace))
            await pilot.pause()
            seen["labels"] = [str(label.content) for label in app.screen.query(Label)]
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    row = next(label for label in seen["labels"] if "Auth decision" in label)
    assert "trusted" in row  # trust derived from lifecycle fields
    assert "2099-01-01" in row  # expiry (review_after)
    assert "sess-auth" in row  # origin session


def test_memory_screen_type_filter_cycles_with_t(workspace) -> None:
    """TUI-FLOW-005: pressing t cycles the type filter — the list narrows to
    one type and the active filter is displayed; cycling past the last type
    returns to all."""
    from textual.widgets import Label, Static

    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.screens.memory import MemoryBrowserScreen

    _seed(workspace, title="Auth decision", lifecycle_state="active", type="decision")
    _seed(workspace, title="Plain note", lifecycle_state="proposed", type="mem_save")
    seen: dict[str, object] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="home")
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(MemoryBrowserScreen(root=workspace))
            await pilot.pause()
            await pilot.press("t")  # filter: decision (types sorted)
            await pilot.pause()
            seen["filtered"] = [str(label.content) for label in app.screen.query(Label)]
            seen["status"] = str(app.screen.query_one("#memory-status", Static).content)
            await pilot.press("t")  # filter: mem_save
            await pilot.pause()
            await pilot.press("t")  # back to all
            await pilot.pause()
            seen["all"] = [str(label.content) for label in app.screen.query(Label)]
            await pilot.press("q")
            await pilot.press("q")

    asyncio.run(scenario())
    filtered = [label for label in seen["filtered"] if "#" in label]
    assert any("Auth decision" in label for label in filtered)
    assert not any("Plain note" in label for label in filtered)
    assert "decision" in str(seen["status"])
    assert any("Plain note" in label for label in seen["all"])

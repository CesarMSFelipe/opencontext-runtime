"""Tests for the unified Textual configuration screen.

Driven headless through Textual's ``run_test`` pilot (wrapped in ``asyncio.run`` so
no pytest-asyncio is needed). Proves the 3-column Miller navigation builds, a select
applies and persists, and the app exits cleanly — the failure mode we guard against
is a full-screen app that hangs or crashes in CI.
"""

from __future__ import annotations

import asyncio

import pytest

textual = pytest.importorskip("textual", reason="textual not installed")


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Give every test its own config. UserConfigStore.CONFIG_FILE is resolved at
    import time, so a bare HOME monkeypatch is too late — patch the paths directly
    or the tests pollute each other (and the developer's real config)."""
    from opencontext_core.user_prefs import UserConfigStore

    cfg_dir = tmp_path / ".config" / "opencontext"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", cfg_dir / "user-config.json")
    (tmp_path / "opencontext.yaml").write_text("memory:\n  provider: local\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _project(tmp_path):
    return tmp_path


def test_config_screen_builds_three_categories(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from textual.widgets import ListView

    from opencontext_cli.tui.app import OpenContextApp

    monkeypatch.setenv("HOME", str(_project(tmp_path)))
    monkeypatch.chdir(tmp_path)

    seen: dict[str, int] = {}

    async def scenario() -> None:
        app = OpenContextApp(start="config")
        async with app.run_test() as pilot:
            await pilot.pause()
            seen["cats"] = len(app.screen.query_one("#cats", ListView).children)
            await pilot.press("q")

    asyncio.run(scenario())
    assert seen["cats"] == 3  # Setup · Settings · Maintenance


def test_config_screen_select_applies_and_persists(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_core.user_prefs import UserConfigStore

    monkeypatch.setenv("HOME", str(_project(tmp_path)))
    monkeypatch.chdir(tmp_path)

    before = UserConfigStore().load().security_mode

    async def scenario() -> None:
        app = OpenContextApp(start="config")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("down")  # category: Setup → Settings
            await pilot.pause()
            await pilot.press("right")  # focus the settings column (Security)
            await pilot.pause()
            await pilot.press("right")  # focus the options column (security modes)
            await pilot.pause()
            await pilot.press("down")
            await pilot.press("down")  # move to a different mode (enterprise)
            await pilot.pause()
            await pilot.press("enter")  # apply in place
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(scenario())
    after = UserConfigStore().load().security_mode
    assert after != before
    assert after == "enterprise"


def test_native_features_toggle_persists(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.sub_screens import MultiToggleScreen
    from opencontext_core.user_prefs import UserConfigStore

    monkeypatch.setenv("HOME", str(_project(tmp_path)))
    monkeypatch.chdir(tmp_path)
    before = UserConfigStore().load().features.knowledge_graph

    async def scenario() -> None:
        app = OpenContextApp(start="config")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("down")  # Settings
            await pilot.pause()
            await pilot.press("right")  # settings column (Security)
            await pilot.pause()
            await pilot.press("down")  # Features
            await pilot.pause()
            await pilot.press("enter")  # open the native toggle screen
            await pilot.pause()
            assert isinstance(app.screen, MultiToggleScreen)
            await pilot.press("space")  # toggle Knowledge Graph off
            await pilot.press("s")  # save
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(scenario())
    assert UserConfigStore().load().features.knowledge_graph != before


def test_native_tokens_input_persists(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.sub_screens import TextValueScreen
    from opencontext_core.user_prefs import UserConfigStore

    monkeypatch.setenv("HOME", str(_project(tmp_path)))
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = OpenContextApp(start="config")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            await pilot.press("down")
            await pilot.press("down")  # Token budgets
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, TextValueScreen)
            for _ in range(8):
                await pilot.press("backspace")
            for ch in "9000":
                await pilot.press(ch)
            await pilot.press("enter")  # submit
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(scenario())
    assert UserConfigStore().load().default_token_budget == 9000


def test_native_models_two_step_persists(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from opencontext_cli.tui.app import OpenContextApp
    from opencontext_cli.tui.sub_screens import ModelsScreen
    from opencontext_core.user_prefs import UserConfigStore

    monkeypatch.setenv("HOME", str(_project(tmp_path)))
    monkeypatch.chdir(tmp_path)

    async def scenario() -> None:
        app = OpenContextApp(start="config")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            for _ in range(3):
                await pilot.press("down")  # Providers & models
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ModelsScreen)
            await pilot.press("down")  # provider → openai
            await pilot.pause()
            await pilot.press("enter")  # pick provider → populates model list
            await pilot.pause()
            await pilot.press("enter")  # pick first model → save + dismiss
            await pilot.pause()
            await pilot.press("q")

    asyncio.run(scenario())
    prefs = UserConfigStore().load()
    assert prefs.default_provider == "openai"
    assert prefs.default_model in {"gpt-4o", "gpt-4o-mini", "o1"}

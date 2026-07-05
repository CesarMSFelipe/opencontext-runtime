"""Config wizard chrome contract.

``opencontext config wizard`` — also launched from the config TUI via
``app.suspend()`` — must render the shared wizard frame for every section, so
the TUI aspect (logo + status + Step N/M + detail card) survives the suspend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from opencontext_core import wizard as wiz


@pytest.fixture()
def _isolated_prefs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from opencontext_core.user_prefs import UserConfigStore

    cfg_dir = tmp_path / ".config" / "opencontext"
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", cfg_dir / "user-config.json")
    monkeypatch.chdir(tmp_path)


def _stub_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wiz.prompts, "select", lambda m, c, **k: k.get("default"))
    monkeypatch.setattr(wiz.prompts, "checkbox", lambda m, c, **k: list(k.get("defaults", [])))
    monkeypatch.setattr(wiz.prompts, "int_input", lambda m, **k: k.get("default"))
    monkeypatch.setattr(wiz.prompts, "confirm", lambda m, **k: True)


def test_run_wizard_frames_every_section(
    _isolated_prefs: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    frames: list[tuple[int, int, str]] = []

    def fake_render(i: int, t: int, step: Any, status_line: Any = None, **kw: Any) -> bool:
        frames.append((i, t, step.title))
        return True

    monkeypatch.setattr(wiz, "render_frame", fake_render)
    monkeypatch.setattr(wiz, "_plugin_wizard_step", lambda prefs: None)
    _stub_prompts(monkeypatch)

    wiz.run_wizard()

    assert [(i, t) for i, t, _ in frames] == [(n, 6) for n in range(1, 7)]
    assert [title for _, _, title in frames] == [
        "Security & privacy",
        "Features",
        "Token budgets",
        "Agent integrations",
        "Plugins",
        "Learning & optimization",
    ]


def test_reconfigure_section_renders_single_step_frame(
    _isolated_prefs: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    frames: list[tuple[int, int, str]] = []
    monkeypatch.setattr(
        wiz,
        "render_frame",
        lambda i, t, step, status_line=None, **kw: frames.append((i, t, step.title)) or True,
    )
    _stub_prompts(monkeypatch)

    wiz.reconfigure("tokens")

    assert frames == [(1, 1, "Token budgets")]


def test_config_tui_wizard_leaf_launches_framed_wizard() -> None:
    """The config TUI 'Full setup wizard' leaf must point at run_wizard, which
    renders the shared frame — the aspect that survives ``app.suspend()``."""
    pytest.importorskip("textual")
    from opencontext_cli.tui.config_model import build_config_model

    model = build_config_model()
    leaves = {leaf.key: leaf for cat in model for leaf in cat.leaves}
    assert leaves["wizard"].run is wiz.run_wizard

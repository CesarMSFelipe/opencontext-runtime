"""Shared wizard-frame contract.

Every interactive wizard step renders the same chrome as the config TUI:
compact brand logo + live status line, a "Step N/M" progress trail, and a
detail card in the info-pane format (Current / Effect / Recommended /
Risk / note / CLI). Non-TTY runs render nothing — prompts are skipped there
anyway, so the frame must never pollute piped/CI output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.dx import wizard_frame
from opencontext_core.dx.wizard_frame import (
    WizardStep,
    frame_lines,
    render_frame,
    wizard_status_line,
)


def _step(**overrides: str) -> WizardStep:
    base = {
        "title": "Security mode",
        "current": "private_project",
        "effect": "Controls external access and provider safety defaults.",
        "recommended": "private_project for solo work.",
        "risk": "Lower postures may allow more integrations.",
        "cli": "opencontext config set security_mode <mode>",
    }
    base.update(overrides)
    return WizardStep(**base)  # type: ignore[arg-type]


class TestWizardStep:
    def test_detail_pairs_are_in_info_pane_order(self) -> None:
        pairs = _step().detail_pairs()
        assert [label for label, _ in pairs] == [
            "Current",
            "Effect",
            "Recommended",
            "Risk / note",
            "CLI",
        ]

    def test_detail_pairs_skip_empty_fields(self) -> None:
        pairs = _step(current="", risk="").detail_pairs()
        assert [label for label, _ in pairs] == ["Effect", "Recommended", "CLI"]

    def test_with_current_returns_updated_copy(self) -> None:
        step = _step(current="")
        updated = step.with_current("en")
        assert updated.current == "en"
        assert step.current == ""  # frozen original untouched


class TestFrameLines:
    def test_includes_logo_status_progress_and_card(self) -> None:
        lines = frame_lines(2, 5, _step(), "demo · installed · KG: healthy")
        text = "\n".join(lines)
        assert "◉──◉──◉" in text  # compact brand logo
        assert "demo · installed · KG: healthy" in text
        assert "Step 2/5" in text
        assert "Security mode" in text
        # Info-pane format: dim labels, plain values.
        assert "Current:[/] private_project" in text
        assert "Effect:[/] Controls external access" in text
        assert "Risk / note:[/]" in text
        assert "CLI:[/] opencontext config set security_mode <mode>" in text

    def test_progress_dots_track_step_index(self) -> None:
        text = "\n".join(frame_lines(2, 3, _step(), ""))
        assert text.count("●") == 2
        assert text.count("○") == 1


class TestRenderFrame:
    def test_non_tty_renders_nothing(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(wizard_frame, "_is_tty", lambda: False)
        assert render_frame(1, 3, _step()) is False
        assert capsys.readouterr().out == ""

    def test_tty_renders_frame(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(wizard_frame, "_is_tty", lambda: True)
        assert render_frame(1, 3, _step(), "status here", clear=False) is True
        out = capsys.readouterr().out
        assert "Step 1/3" in out
        assert "status here" in out
        assert "Security mode" in out
        assert "opencontext config set security_mode" in out


class TestWizardStatusLine:
    def test_uninstalled_project_status(self, tmp_path: Path) -> None:
        line = wizard_status_line(tmp_path)
        assert tmp_path.name in line
        assert "not installed" in line
        assert "KG:" in line
        assert "Memory:" in line
        assert "Flow:" in line

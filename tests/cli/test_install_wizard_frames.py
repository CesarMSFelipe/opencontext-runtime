"""Install wizard chrome contract.

Every interactive install step must render the shared wizard frame (brand
logo + status line + Step N/M + detail card) instead of a bare prompt.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import opencontext_cli.main as main_mod
from opencontext_core.dx import wizard_frame


class _FakeProvider:
    source = "fallback"


def test_install_wizard_frames_every_step(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    frames: list[tuple[int, int, str]] = []

    def fake_render(
        step_index: int, total: int, step: Any, status_line: Any = None, **kwargs: Any
    ) -> bool:
        frames.append((step_index, total, step.title))
        return True

    monkeypatch.setattr(wizard_frame, "render_frame", fake_render)
    monkeypatch.setattr(wizard_frame, "wizard_status_line", lambda root=".": "status")
    monkeypatch.setattr(
        "opencontext_core.providers.detect.detect_provider", lambda: _FakeProvider()
    )
    from opencontext_core import prompts

    monkeypatch.setattr(prompts, "select", lambda message, choices, **kw: kw.get("default"))
    monkeypatch.setattr(prompts, "secret", lambda message: "")
    # The wizard records choices via env vars; register them with monkeypatch
    # so the test never leaks state.
    monkeypatch.setenv("_OC_WIZARD_EDITOR", "")
    monkeypatch.setenv("_OC_WIZARD_SDD_PROFILE", "")

    args = SimpleNamespace(root=str(tmp_path))
    main_mod._install_wizard(args, main_mod.console)

    assert frames == [
        (1, 4, "Interface language"),
        (2, 4, "AI coding editor"),
        (3, 4, "Model routing (SDD phases)"),
        (4, 4, "LLM provider key"),
    ]


def test_provider_step_skipped_when_provider_detected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frames: list[str] = []
    monkeypatch.setattr(
        wizard_frame,
        "render_frame",
        lambda i, t, step, status_line=None, **kw: frames.append(step.title) or True,
    )
    monkeypatch.setattr(wizard_frame, "wizard_status_line", lambda root=".": "status")
    monkeypatch.setattr(
        "opencontext_core.providers.detect.detect_provider",
        lambda: SimpleNamespace(source="env"),
    )
    from opencontext_core import prompts

    monkeypatch.setattr(prompts, "select", lambda message, choices, **kw: kw.get("default"))
    monkeypatch.setenv("_OC_WIZARD_EDITOR", "")
    monkeypatch.setenv("_OC_WIZARD_SDD_PROFILE", "")

    main_mod._install_wizard(SimpleNamespace(root=str(tmp_path)), main_mod.console)

    assert "LLM provider key" not in frames

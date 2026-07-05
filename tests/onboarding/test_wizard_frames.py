"""Onboarding wizard chrome contract.

Interactive steps render the shared wizard frame with a truthful ``Step N/M``:
overridden choices (CLI flags) never count, and the memory step only exists
when a co-resident Engram install is detected.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import opencontext_core.onboarding.wizard as onb
from opencontext_core.onboarding.wizard import InteractiveOnboardingWizard


@pytest.fixture()
def wizard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> InteractiveOnboardingWizard:
    w = InteractiveOnboardingWizard(root=tmp_path)
    w._interactive = True
    monkeypatch.setattr(onb, "wizard_status_line", lambda root=".": "status")
    monkeypatch.setattr("opencontext_core.memory.engram_bridge.detect_engram", lambda: False)
    return w


def test_plan_counts_only_steps_that_prompt(wizard: InteractiveOnboardingWizard) -> None:
    wizard._plan_steps({"template": "generic", "tdd": "strict"})
    assert wizard._step_plan == ["security_mode", "agents"]


def test_plan_includes_memory_only_when_engram_detected(
    wizard: InteractiveOnboardingWizard, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("opencontext_core.memory.engram_bridge.detect_engram", lambda: True)
    wizard._plan_steps({})
    assert wizard._step_plan == ["template", "security_mode", "tdd", "agents", "memory"]


def test_frame_renders_truthful_position(
    wizard: InteractiveOnboardingWizard, monkeypatch: pytest.MonkeyPatch
) -> None:
    frames: list[tuple[int, int, str]] = []
    monkeypatch.setattr(
        onb, "render_frame", lambda i, t, step, status: frames.append((i, t, step.title)) or True
    )
    wizard._step_plan = ["security_mode", "tdd"]
    wizard._frame("tdd")
    assert frames == [(2, 2, "TDD mode")]


def test_frame_skips_unplanned_and_non_interactive_steps(
    wizard: InteractiveOnboardingWizard, monkeypatch: pytest.MonkeyPatch
) -> None:
    frames: list[str] = []
    monkeypatch.setattr(
        onb, "render_frame", lambda i, t, step, status: frames.append(step.title) or True
    )
    wizard._step_plan = ["tdd"]
    wizard._frame("agents")  # not planned (overridden)
    wizard._interactive = False
    wizard._frame("tdd")  # non-interactive
    assert frames == []

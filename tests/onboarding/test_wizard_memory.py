"""Wizard memory step: memory provider defaults to 'auto' (couple to a co-resident
Engram when present, else OpenContext's own local memory); the interactive wizard
still offers an explicit choice when Engram is detected."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.config import load_config
from opencontext_core.onboarding import wizard as wizard_mod
from opencontext_core.onboarding.service import OnboardingOptions, OnboardingService
from opencontext_core.onboarding.wizard import InteractiveOnboardingWizard


def test_default_memory_provider_is_auto(tmp_path: Path) -> None:
    # No explicit choice -> 'auto': couple to a co-resident Engram when present,
    # else OpenContext's own local memory (the factory degrades gracefully).
    OnboardingService().run(OnboardingOptions(root=tmp_path, force_agent_files=True))
    assert load_config(tmp_path / "opencontext.yaml").memory.provider == "auto"


def test_service_honors_engram_choice(tmp_path: Path) -> None:
    OnboardingService().run(
        OnboardingOptions(root=tmp_path, memory_provider="engram", force_agent_files=True)
    )
    assert load_config(tmp_path / "opencontext.yaml").memory.provider == "engram"


def test_air_gapped_forces_local_memory(tmp_path: Path) -> None:
    # Air-gapped must not couple to an external Engram even if the user picked it.
    OnboardingService().run(
        OnboardingOptions(
            root=tmp_path,
            template="air_gapped",
            security_mode="air_gapped",
            memory_provider="engram",
            force_agent_files=True,
        )
    )
    assert load_config(tmp_path / "opencontext.yaml").memory.provider == "local"


def test_choose_memory_provider_non_interactive_is_local(tmp_path: Path) -> None:
    wizard = InteractiveOnboardingWizard(root=tmp_path)
    wizard._interactive = False
    assert wizard._choose_memory_provider() == "local"


def test_choose_memory_provider_no_engram_returns_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Interactive, but no Engram present -> no prompt, use OpenContext memory.
    monkeypatch.setattr("opencontext_core.memory.engram_bridge.detect_engram", lambda: False)
    wizard = InteractiveOnboardingWizard(root=tmp_path)
    wizard._interactive = True
    assert wizard._choose_memory_provider() == "local"


def test_choose_memory_provider_offers_coexistence_when_engram_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Engram present -> the user is offered the choice and it is honored.
    monkeypatch.setattr("opencontext_core.memory.engram_bridge.detect_engram", lambda: True)
    monkeypatch.setattr(wizard_mod.prompts, "select", lambda *a, **k: "engram")
    wizard = InteractiveOnboardingWizard(root=tmp_path)
    wizard._interactive = True
    assert wizard._choose_memory_provider() == "engram"

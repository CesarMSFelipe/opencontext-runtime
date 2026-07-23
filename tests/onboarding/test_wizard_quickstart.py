"""Tests for the InteractiveOnboardingWizard quick-start path.

Rodaja 6 — "just let the user work". A brand-new user must be able to start
with ZERO forced decisions: the wizard offers a single choice up front —
recommended defaults vs customize — and when defaults are accepted it applies a
sane config WITHOUT walking every per-step selector. The full customize path
(``_choose_template`` / ``_choose_security_mode`` / ...) stays reachable and
unchanged; this only layers a fast path on top.

These tests exercise behaviour (the applied options), never interactive
keypresses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from opencontext_core.onboarding.wizard import InteractiveOnboardingWizard


class _RecordingService:
    """Captures the OnboardingOptions the wizard hands to the service."""

    def __init__(self) -> None:
        self.options: Any = None

    def run(self, options: Any) -> Any:
        from opencontext_core.onboarding.service import OnboardingResult

        self.options = options
        return OnboardingResult(root=str(options.root))


@pytest.fixture
def recording_service(monkeypatch: pytest.MonkeyPatch) -> _RecordingService:
    svc = _RecordingService()
    # The wizard binds OnboardingService at module import (see wizard.py top),
    # so patch the name in the wizard module — matching test_wizard.py.
    monkeypatch.setattr(
        "opencontext_core.onboarding.wizard.OnboardingService",
        lambda: svc,
    )
    return svc


# ---------------------------------------------------------------------------
# quickstart_defaults() — the sane-defaults contract
# ---------------------------------------------------------------------------


class TestQuickstartDefaults:
    def test_quickstart_defaults_are_sane_and_complete(self) -> None:
        """The default set covers every decision with the recommended value, so
        no per-step prompt is required to produce a working config."""
        defaults = InteractiveOnboardingWizard.quickstart_defaults()

        assert defaults["template"] == "generic"
        assert defaults["security_mode"] == "private_project"
        assert defaults["tdd"] == "ask"
        # memory 'auto' so a co-resident Engram is used when present (goal: not
        # forced to 'local', not an upfront decision).
        assert defaults["memory_provider"] == "auto"
        # Agents default to whatever is actually detected on this host.
        assert isinstance(defaults["agents"], list)
        assert defaults["agents"]  # non-empty (falls back to opencode)

    def test_quickstart_defaults_agents_match_detection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # quickstart_defaults resolves agents via default_active_clients imported
        # from the service module; patch it at its source so the wizard sees it.
        monkeypatch.setattr(
            "opencontext_core.onboarding.service.default_active_clients",
            lambda: ["claude-code", "codex"],
        )
        defaults = InteractiveOnboardingWizard.quickstart_defaults()
        assert defaults["agents"] == ["claude-code", "codex"]


# ---------------------------------------------------------------------------
# run() quick-start branch — applies defaults WITHOUT per-step prompts
# ---------------------------------------------------------------------------


class TestQuickstartRun:
    def test_quickstart_applies_defaults_without_prompting_each_step(
        self, tmp_path: Path, recording_service: _RecordingService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the user picks the recommended path, run() must NOT invoke any of
        the per-step selectors — it applies the defaults directly."""
        wizard = InteractiveOnboardingWizard(root=tmp_path)
        # Force the interactive gate to return the quick-start choice.
        wizard._interactive = True
        monkeypatch.setattr(wizard, "_choose_setup_mode", lambda: "quickstart")

        # Any per-step selector call is a contract violation on the fast path.
        def _boom(*_a: Any, **_k: Any) -> Any:
            raise AssertionError("per-step selector called on quick-start path")

        monkeypatch.setattr(wizard, "_choose_template", _boom)
        monkeypatch.setattr(wizard, "_choose_security_mode", _boom)
        monkeypatch.setattr(wizard, "_choose_tdd_mode", _boom)
        monkeypatch.setattr(wizard, "_choose_agents", _boom)
        monkeypatch.setattr(wizard, "_choose_memory_provider", _boom)
        # Silence chrome.
        monkeypatch.setattr(wizard, "_show_welcome", lambda: None)
        monkeypatch.setattr(wizard, "_show_summary", lambda _r: None)

        wizard.run()

        opts = recording_service.options
        assert opts is not None, "service was never run"
        assert opts.template == "generic"
        assert opts.security_mode == "private_project"
        assert opts.tdd_mode == "ask"
        assert opts.memory_provider == "auto"
        assert opts.active_clients  # detected agents, non-empty

    def test_customize_path_still_walks_per_step_selectors(
        self, tmp_path: Path, recording_service: _RecordingService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Choosing 'customize' preserves the existing per-step flow — nothing is
        removed, options remain reachable."""
        wizard = InteractiveOnboardingWizard(root=tmp_path)
        wizard._interactive = True
        monkeypatch.setattr(wizard, "_choose_setup_mode", lambda: "customize")

        called: list[str] = []
        monkeypatch.setattr(
            wizard, "_choose_template", lambda: called.append("template") or "enterprise"
        )
        monkeypatch.setattr(
            wizard,
            "_choose_security_mode",
            lambda: called.append("security") or "enterprise",
        )
        monkeypatch.setattr(wizard, "_choose_tdd_mode", lambda: called.append("tdd") or "strict")
        monkeypatch.setattr(
            wizard, "_choose_agents", lambda: called.append("agents") or ["opencode"]
        )
        monkeypatch.setattr(
            wizard,
            "_choose_memory_provider",
            lambda: called.append("memory") or "local",
        )
        monkeypatch.setattr(wizard, "_show_welcome", lambda: None)
        monkeypatch.setattr(wizard, "_show_summary", lambda _r: None)

        wizard.run()

        assert called == ["template", "security", "tdd", "agents", "memory"]
        opts = recording_service.options
        assert opts.template == "enterprise"
        assert opts.security_mode == "enterprise"
        assert opts.tdd_mode == "strict"

    def test_explicit_overrides_skip_the_gate_entirely(
        self, tmp_path: Path, recording_service: _RecordingService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the caller passes explicit choices (CLI flags), the setup-mode gate
        must NOT be shown — the user already decided."""
        wizard = InteractiveOnboardingWizard(root=tmp_path)
        wizard._interactive = True

        def _gate_boom() -> str:
            raise AssertionError("setup-mode gate shown despite explicit overrides")

        monkeypatch.setattr(wizard, "_choose_setup_mode", _gate_boom)
        monkeypatch.setattr(wizard, "_show_welcome", lambda: None)
        monkeypatch.setattr(wizard, "_show_summary", lambda _r: None)

        wizard.run(
            template="enterprise",
            security_mode="enterprise",
            tdd="strict",
            agents=["opencode"],
            memory_provider="local",
        )

        opts = recording_service.options
        assert opts.template == "enterprise"
        assert opts.security_mode == "enterprise"

    def test_non_interactive_does_not_show_gate(
        self, tmp_path: Path, recording_service: _RecordingService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-interactive (CI / piped) never prompts — including the new gate."""
        wizard = InteractiveOnboardingWizard(root=tmp_path)
        wizard._interactive = False

        def _gate_boom() -> str:
            raise AssertionError("setup-mode gate shown in non-interactive mode")

        monkeypatch.setattr(wizard, "_choose_setup_mode", _gate_boom)
        monkeypatch.setattr(wizard, "_show_welcome", lambda: None)
        monkeypatch.setattr(wizard, "_show_summary", lambda _r: None)

        wizard.run(non_interactive=True)

        opts = recording_service.options
        assert opts is not None
        # Non-interactive defaults are unchanged (generic / private_project / ask).
        assert opts.template == "generic"
        assert opts.security_mode == "private_project"

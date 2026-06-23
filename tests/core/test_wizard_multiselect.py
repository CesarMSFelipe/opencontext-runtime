"""Plugin and feature reconfiguration must use one navigable multiselect.

Regression guard: both paths once asked N sequential yes/no confirms instead of
a single checkbox (the user explicitly requested multiselect for picking
plugins). These drive the logic with the selector stubbed so a slip back to
per-item confirms fails in CI instead of in a user's terminal.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from opencontext_core import wizard


def test_reconfigure_features_uses_checkbox(monkeypatch: pytest.MonkeyPatch) -> None:
    prefs = SimpleNamespace(
        features=SimpleNamespace(knowledge_graph=False, call_graph=True, learning_system=True)
    )
    saved: dict[str, object] = {}
    monkeypatch.setattr(
        wizard,
        "UserConfigStore",
        lambda: SimpleNamespace(load=lambda: prefs, save=lambda p: saved.__setitem__("p", p)),
    )
    calls: dict[str, object] = {}

    def fake_checkbox(message: str, choices: list, **kwargs: object) -> list[str]:
        calls["choices"] = [c[0] for c in choices]
        calls["defaults"] = list(kwargs.get("defaults", ()))  # type: ignore[arg-type]
        return ["knowledge_graph"]

    monkeypatch.setattr(wizard.prompts, "checkbox", fake_checkbox)

    wizard.reconfigure("features")

    # One multiselect over the three feature keys, pre-checked from current state.
    assert calls["choices"] == ["knowledge_graph", "call_graph", "learning_system"]
    assert set(calls["defaults"]) == {"call_graph", "learning_system"}  # type: ignore[arg-type]
    # Selection applied verbatim: only knowledge_graph ends up on.
    assert prefs.features.knowledge_graph is True
    assert prefs.features.call_graph is False
    assert prefs.features.learning_system is False
    assert saved["p"] is prefs


def test_plugin_step_uses_single_checkbox(monkeypatch: pytest.MonkeyPatch) -> None:
    available = [
        SimpleNamespace(
            name="alpha", description="Alpha plugin", versions=[SimpleNamespace(version="1.0")]
        ),
        SimpleNamespace(
            name="beta", description="Beta plugin", versions=[SimpleNamespace(version="2.0")]
        ),
    ]
    monkeypatch.setattr(wizard, "PluginRegistry", lambda: SimpleNamespace(discover=lambda: []))
    monkeypatch.setattr(
        wizard,
        "RegistryFetcher",
        lambda: SimpleNamespace(fetch=lambda: available, search=lambda: available),
    )
    installed: list[str] = []
    monkeypatch.setattr(
        wizard,
        "PluginInstaller",
        lambda reg: SimpleNamespace(
            install_from_registry=lambda name: (
                installed.append(name) or SimpleNamespace(status="installed", message="ok")
            )
        ),
    )
    monkeypatch.setattr(wizard, "_ask_bool", lambda q, d=True: d)

    checkbox_calls: list[list[str]] = []

    def fake_checkbox(message: str, choices: list, **kwargs: object) -> list[str]:
        checkbox_calls.append([c[0] for c in choices])
        return ["beta"]

    monkeypatch.setattr(wizard.prompts, "checkbox", fake_checkbox)

    prefs = SimpleNamespace(check_updates=True, auto_update_plugins=False)
    wizard._plugin_wizard_step(prefs)

    # Exactly one checkbox offering both not-yet-installed plugins (not N confirms).
    assert checkbox_calls == [["alpha", "beta"]]
    # Only the checked plugin installs.
    assert installed == ["beta"]

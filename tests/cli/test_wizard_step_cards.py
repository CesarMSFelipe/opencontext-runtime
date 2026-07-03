"""Guard: every framed interactive flow ships truthful detail cards.

Each wizard/menu flow that renders the shared wizard frame declares its steps
as a module-level registry of ``WizardStep``. Every step must explain what it
does (``effect``) and give the non-interactive equivalent (``cli``) — the same
contract the config TUI info pane fulfils. A new step without a card is a
regression to bare-prompt chrome.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from typing import Any

import pytest

from opencontext_core.dx.wizard_frame import WizardStep

_FLOW_REGISTRIES: list[tuple[str, str]] = [
    ("opencontext_cli.main", "_INSTALL_WIZARD_STEPS"),
    ("opencontext_cli.commands.setup_cmd", "_SETUP_WIZARD_STEPS"),
    ("opencontext_cli.commands.uninstall_cmd", "_UNINSTALL_WIZARD_STEPS"),
    ("opencontext_core.wizard", "_CONFIG_WIZARD_STEPS"),
    ("opencontext_core.onboarding.wizard", "_ONBOARDING_STEP_CARDS"),
]


def _steps(registry: Any) -> Iterable[WizardStep]:
    if isinstance(registry, dict):
        return registry.values()
    return registry


@pytest.mark.parametrize(("module_name", "attr"), _FLOW_REGISTRIES)
def test_flow_declares_step_registry(module_name: str, attr: str) -> None:
    module = importlib.import_module(module_name)
    registry = getattr(module, attr, None)
    assert registry is not None, f"{module_name}.{attr} registry is missing"
    steps = list(_steps(registry))
    assert steps, f"{module_name}.{attr} has no steps"
    assert all(isinstance(s, WizardStep) for s in steps)


@pytest.mark.parametrize(("module_name", "attr"), _FLOW_REGISTRIES)
def test_every_step_carries_effect_and_cli(module_name: str, attr: str) -> None:
    module = importlib.import_module(module_name)
    registry = getattr(module, attr, None)
    if registry is None:
        pytest.fail(f"{module_name}.{attr} registry is missing")
    for step in _steps(registry):
        assert step.title.strip(), f"{module_name}.{attr}: step without a title"
        assert step.effect.strip(), f"{module_name}.{attr}: '{step.title}' has no effect text"
        assert step.cli.strip(), f"{module_name}.{attr}: '{step.title}' has no CLI equivalent"

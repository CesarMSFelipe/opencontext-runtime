"""first_run and setup_completed agree across entry points.

RED first: ``OnboardingService.run`` set ``setup_completed=True`` but left
``first_run=True``; the root ``run_wizard`` set ``first_run=False`` but left
``setup_completed=False``. The two flags disagreed, so different entry points
(``is_first_run`` vs ``_check_first_run``) reached opposite conclusions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from opencontext_core.onboarding.service import OnboardingOptions, OnboardingService


def _isolate_prefs(monkeypatch: Any, tmp_path: Path) -> None:
    from opencontext_core.user_prefs import UserConfigStore

    config_dir = tmp_path / "userconfig"
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", config_dir / "user-config.json")


def test_onboarding_service_reconciles_flags(tmp_path: Path, monkeypatch: Any) -> None:
    _isolate_prefs(monkeypatch, tmp_path)
    from opencontext_core.user_prefs import UserConfigStore

    service = OnboardingService()
    service.run(OnboardingOptions(root=tmp_path / "proj", force_agent_files=True))

    prefs = UserConfigStore().load()
    assert prefs.setup_completed is True
    assert prefs.first_run is False, "first_run must be cleared once setup completes"


def test_root_wizard_non_interactive_exits_2(tmp_path: Path, monkeypatch: Any) -> None:
    """run_wizard(non_interactive=True) now exits 2 with an actionable message.

    Non-interactive wizard is not supported; users must use `config set` or
    edit opencontext.yaml directly.  The old silent-success behavior was
    misleading (applied defaults with no output).
    """
    import pytest

    _isolate_prefs(monkeypatch, tmp_path)
    from opencontext_core import wizard as wizard_mod

    with pytest.raises(SystemExit) as exc_info:
        wizard_mod.run_wizard(non_interactive=True)
    assert exc_info.value.code == 2


def test_mark_configured_sets_both_flags(tmp_path: Path, monkeypatch: Any) -> None:
    _isolate_prefs(monkeypatch, tmp_path)
    from opencontext_core.user_prefs import UserConfigStore

    store = UserConfigStore()
    store.mark_configured()

    prefs = UserConfigStore().load()
    assert prefs.first_run is False
    assert prefs.setup_completed is True

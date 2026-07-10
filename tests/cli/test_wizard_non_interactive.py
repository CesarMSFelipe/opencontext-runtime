"""F5: config wizard --non-interactive must produce non-silent output.

The flag existed but called run_wizard(non_interactive=True) which exited 0 with
no output — making users believe nothing happened. The fix is to exit 2 with an
actionable message so the user knows to use config set / edit YAML instead.
"""

from __future__ import annotations

import pytest


def test_wizard_non_interactive_exits_2_with_actionable_message(tmp_path, monkeypatch, capsys):
    """run_wizard(non_interactive=True) must exit 2 with a stderr message that hints
    at usable alternatives (config set / editing YAML directly) — never silent."""
    from opencontext_core.user_prefs import UserConfigStore

    cfg_dir = tmp_path / "home" / ".config" / "opencontext"
    monkeypatch.setattr(UserConfigStore, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(UserConfigStore, "CONFIG_FILE", cfg_dir / "user-config.json")

    from opencontext_core.wizard import run_wizard

    with pytest.raises(SystemExit) as exc_info:
        run_wizard(non_interactive=True)

    # Must exit with code 2 (explicit honest "not implemented") and a stderr message.
    assert exc_info.value.code == 2
    msg = capsys.readouterr().err
    assert msg.strip(), "expected a non-empty stderr message"
    # Must mention at least one alternative (config set or editing YAML directly).
    assert "config set" in msg or "opencontext.yaml" in msg, (
        f"expected alternatives in stderr message, got: {msg!r}"
    )

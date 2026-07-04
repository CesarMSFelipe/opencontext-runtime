"""Tests for P0.2 fix: _purge_global_state and verify_no_global_traces cover
the product-install paths created by install.sh.

Install.sh creates:
  - ~/.opencontext/venv          (the isolated venv)
  - ~/.local/bin/opencontext     (symlink → venv/bin/opencontext when ~/.local/bin is on PATH)
  - PATH line in shell rc files:
      # OpenContext Runtime
      export PATH="<venv_bin>:$PATH"

Paths NOT created by install.sh (intentionally skipped):
  - ~/.local/bin/oc              (not in install.sh)
  - ~/.cache/opencontext         (not in install.sh)
  - ~/.local/state/opencontext   (not in install.sh)

All tests use a tmp fake-HOME; real HOME is never touched.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _isolate_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Redirect Path.home() / expanduser to *home* on every OS."""
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


# ---------------------------------------------------------------------------
# _purge_global_state — venv removal
# ---------------------------------------------------------------------------


def test_purge_global_state_removes_venv(tmp_path, monkeypatch):
    """_purge_global_state removes ~/.opencontext/venv when present."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    venv = home / ".opencontext" / "venv"
    venv.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")

    from opencontext_cli.commands.uninstall_cmd import _purge_global_state

    removed = _purge_global_state()

    assert not venv.exists()
    assert any("venv" in r for r in removed)


def test_purge_global_state_venv_absent_is_noop(tmp_path, monkeypatch):
    """_purge_global_state does not fail when ~/.opencontext/venv is absent."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    from opencontext_cli.commands.uninstall_cmd import _purge_global_state

    # Should not raise even when venv doesn't exist
    removed = _purge_global_state()
    assert all("venv" not in r for r in removed)


# ---------------------------------------------------------------------------
# _purge_global_state — symlink removal
# ---------------------------------------------------------------------------


def test_purge_global_state_removes_oc_symlink_pointing_into_venv(tmp_path, monkeypatch):
    """_purge_global_state removes ~/.local/bin/opencontext when it is a symlink
    pointing into ~/.opencontext/venv."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    venv_bin = home / ".opencontext" / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_binary = venv_bin / "opencontext"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")

    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    symlink = local_bin / "opencontext"
    symlink.symlink_to(fake_binary)

    from opencontext_cli.commands.uninstall_cmd import _purge_global_state

    removed = _purge_global_state()

    assert not symlink.exists()
    assert any("opencontext" in r and ".local" in r for r in removed)


def test_purge_global_state_leaves_unrelated_bin_symlink(tmp_path, monkeypatch):
    """_purge_global_state does NOT remove ~/.local/bin/opencontext when it
    points somewhere other than ~/.opencontext (e.g. a pipx install)."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    other_dir = tmp_path / "pipx" / "bin"
    other_dir.mkdir(parents=True)
    other_bin = other_dir / "opencontext"
    other_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    symlink = local_bin / "opencontext"
    symlink.symlink_to(other_bin)

    from opencontext_cli.commands.uninstall_cmd import _purge_global_state

    _purge_global_state()

    # Must survive — it does not point into ~/.opencontext
    assert symlink.exists()


def test_purge_global_state_leaves_regular_bin_file(tmp_path, monkeypatch):
    """_purge_global_state does NOT remove ~/.local/bin/opencontext when it is
    a regular file (e.g. pipx wrapper), not a symlink into ~/.opencontext."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    regular = local_bin / "opencontext"
    regular.write_text("#!/bin/sh\nexec /usr/bin/opencontext\n", encoding="utf-8")

    from opencontext_cli.commands.uninstall_cmd import _purge_global_state

    _purge_global_state()

    assert regular.exists()


# ---------------------------------------------------------------------------
# _purge_global_state — rc PATH line removal
# ---------------------------------------------------------------------------


def test_purge_global_state_removes_path_export_from_bashrc(tmp_path, monkeypatch):
    """_purge_global_state strips the '# OpenContext Runtime' + PATH export from .bashrc."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    venv_bin = str(home / ".opencontext" / "venv" / "bin")
    bashrc = home / ".bashrc"
    bashrc.write_text(
        'export FOO=bar\n\n# OpenContext Runtime\nexport PATH="'
        + venv_bin
        + ':$PATH"\nexport BAR=baz\n',
        encoding="utf-8",
    )

    from opencontext_cli.commands.uninstall_cmd import _purge_global_state

    _purge_global_state()

    content = bashrc.read_text(encoding="utf-8")
    assert "# OpenContext Runtime" not in content
    assert "opencontext" not in content.lower() or "opencontext" not in content
    # Unrelated content must survive
    assert "FOO=bar" in content
    assert "BAR=baz" in content


def test_purge_global_state_removes_path_export_from_zshrc(tmp_path, monkeypatch):
    """_purge_global_state strips the OC PATH block from .zshrc."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    venv_bin = str(home / ".opencontext" / "venv" / "bin")
    zshrc = home / ".zshrc"
    zshrc.write_text(
        '# my zsh config\n\n# OpenContext Runtime\nexport PATH="' + venv_bin + ':$PATH"\n# end\n',
        encoding="utf-8",
    )

    from opencontext_cli.commands.uninstall_cmd import _purge_global_state

    _purge_global_state()

    content = zshrc.read_text(encoding="utf-8")
    assert "# OpenContext Runtime" not in content
    assert "# my zsh config" in content
    assert "# end" in content


def test_purge_global_state_rc_unrelated_content_survives(tmp_path, monkeypatch):
    """Unrelated rc content is never touched — only the OC block is removed."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    bashrc = home / ".bashrc"
    original = "alias ls='ls -la'\nexport PATH=\"/usr/local/bin:$PATH\"\n"
    bashrc.write_text(original, encoding="utf-8")

    from opencontext_cli.commands.uninstall_cmd import _purge_global_state

    _purge_global_state()

    # No OC block was present — file must be unchanged
    assert bashrc.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# verify_no_global_traces — detects product-install residue
# ---------------------------------------------------------------------------


def test_verify_no_global_traces_detects_venv(tmp_path, monkeypatch):
    """verify_no_global_traces reports ~/.opencontext/venv as residue."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    venv = home / ".opencontext" / "venv"
    venv.mkdir(parents=True)

    from opencontext_cli.commands.uninstall_cmd import verify_no_global_traces

    residue = verify_no_global_traces([])
    assert any("venv" in r for r in residue)


def test_verify_no_global_traces_detects_oc_symlink(tmp_path, monkeypatch):
    """verify_no_global_traces reports ~/.local/bin/opencontext pointing into
    ~/.opencontext as residue."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    venv_bin = home / ".opencontext" / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    target = venv_bin / "opencontext"
    target.write_text("#!/bin/sh\n", encoding="utf-8")

    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "opencontext").symlink_to(target)

    from opencontext_cli.commands.uninstall_cmd import verify_no_global_traces

    residue = verify_no_global_traces([])
    assert any(".local" in r and "opencontext" in r for r in residue)


def test_verify_no_global_traces_clean_after_purge(tmp_path, monkeypatch):
    """After _purge_global_state, verify_no_global_traces sees no product-install residue."""
    home = tmp_path / "home"
    home.mkdir()
    _isolate_home(monkeypatch, home)

    # Create all install.sh artifacts
    venv = home / ".opencontext" / "venv"
    venv.mkdir(parents=True)
    venv_bin = venv / "bin"
    venv_bin.mkdir()
    fake_binary = venv_bin / "opencontext"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "opencontext").symlink_to(fake_binary)

    from opencontext_cli.commands.uninstall_cmd import _purge_global_state, verify_no_global_traces

    _purge_global_state()

    residue = verify_no_global_traces([])
    # Filter to product-install paths specifically
    product_residue = [r for r in residue if "venv" in r or (".local" in r and "opencontext" in r)]
    assert product_residue == []


# ---------------------------------------------------------------------------
# --full --dry-run lists product-install paths in the plan
# ---------------------------------------------------------------------------


def test_full_dry_run_lists_venv_in_plan(tmp_path, monkeypatch, capsys):
    """--full --dry-run with --global-state lists the venv in would_remove."""
    import opencontext_cli.main as main_mod

    monkeypatch.setattr(main_mod, "_resolve_flag", lambda v, _: v)
    args = SimpleNamespace(
        full=True,
        verify=False,
        yes=False,
        dry_run=True,
        json=True,
        scope="local",
        global_state=True,
        root=str(tmp_path),
        all_agents=False,
        agents=[],
        purge=False,
    )
    from opencontext_cli.commands.uninstall_cmd import handle_uninstall

    handle_uninstall(args)

    import json as _json

    out = capsys.readouterr().out
    data = _json.loads(out)
    assert data["dry_run"] is True
    # venv path must appear in the plan
    assert any("venv" in str(item) for item in data["would_remove"])

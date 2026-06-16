"""Per-agent ignore files keep secrets/build paths out of agent context."""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core.configurator import constants
from opencontext_core.configurator.service import Configurator


def _configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, agent: str) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    project = tmp_path / "proj"
    project.mkdir()
    Configurator(project_root=project).configure([agent], scope="local")
    return project / str(constants.ignore_filename(agent))


def test_configure_writes_cursor_ignore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _configure(tmp_path, monkeypatch, "cursor")
    assert path.name == ".cursorignore"
    body = path.read_text(encoding="utf-8")
    assert ".env" in body and "secrets/" in body
    assert "# opencontext:ignore:start" in body


def test_ignore_preserves_user_patterns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".cursorignore").write_text("my_private_dir/\n", encoding="utf-8")

    cfg = Configurator(project_root=project)
    cfg.configure(["cursor"], scope="local")
    body = (project / ".cursorignore").read_text(encoding="utf-8")
    assert "my_private_dir/" in body  # user pattern survives
    assert ".env" in body  # ours added

    # Uninstall strips only our block, leaving the user's pattern.
    cfg.deconfigure(["cursor"], scope="local")
    after = (project / ".cursorignore").read_text(encoding="utf-8")
    assert "my_private_dir/" in after
    assert "opencontext:ignore" not in after
    assert ".env" not in after


def test_agent_without_native_ignore_writes_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # claude-code has no native ignore file; configuring it must not create one.
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    project = tmp_path / "proj"
    project.mkdir()
    Configurator(project_root=project).configure(["claude-code"], scope="local")
    assert constants.ignore_filename("claude-code") is None
    assert not list(project.glob("*ignore"))

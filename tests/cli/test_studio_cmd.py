"""Tests for the ``opencontext studio`` CLI command (PR-014 — SPEC-STU-014-01)."""

from __future__ import annotations

from pathlib import Path

from opencontext_cli.commands.studio_cmd import run_studio
from opencontext_core.studio.server import serve, studio_url


def test_run_studio_no_browser_prints_url_no_open(tmp_path: Path, capsys, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    # Build + degrade without blocking on uvicorn (_run=False inside serve).
    url = serve(tmp_path, port=8799, open_browser=False, _run=False)
    out = capsys.readouterr().out
    assert url == "http://127.0.0.1:8799"
    assert url in out
    assert opened == []  # --no-browser must not open a browser


def test_serve_open_browser_degrades_when_unavailable(tmp_path: Path, monkeypatch) -> None:
    def _boom(url: str) -> None:
        raise RuntimeError("no display")

    monkeypatch.setattr("webbrowser.open", _boom)
    # A failing browser open must degrade silently, not raise.
    url = serve(tmp_path, port=8801, open_browser=True, _run=False)
    assert url == studio_url(8801)


def test_run_studio_delegates_to_serve(tmp_path: Path, monkeypatch) -> None:
    calls: dict[str, object] = {}

    def _fake_serve(root, *, port, open_browser):
        calls.update(root=str(root), port=port, open_browser=open_browser)
        return studio_url(port)

    monkeypatch.setattr("opencontext_core.studio.server.serve", _fake_serve)
    result = run_studio(tmp_path, port=9100, no_browser=True)
    assert result == "http://127.0.0.1:9100"
    assert calls == {"root": str(tmp_path), "port": 9100, "open_browser": False}

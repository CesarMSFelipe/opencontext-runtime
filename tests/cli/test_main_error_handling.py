"""main() turns an unexpected error into a friendly, actionable message."""

from __future__ import annotations

import sys

import pytest

import opencontext_cli.main as m


def _boom(_args: object) -> None:
    raise RuntimeError("boom")


def test_unexpected_error_is_friendly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(sys, "argv", ["opencontext", "doctor"])
    monkeypatch.delenv("OPENCONTEXT_DEBUG", raising=False)
    monkeypatch.setattr(m, "_dispatch", _boom)

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "Unexpected error: boom" in err
    assert "OPENCONTEXT_DEBUG=1" in err
    assert "Traceback" not in err  # no scary stack trace


def test_debug_env_reraises_for_developers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["opencontext", "doctor"])
    monkeypatch.setenv("OPENCONTEXT_DEBUG", "1")
    monkeypatch.setattr(m, "_dispatch", _boom)

    with pytest.raises(RuntimeError, match="boom"):
        m.main()

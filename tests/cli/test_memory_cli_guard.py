"""M4: id-targeted markdown memory mutations must not crash on a SQLite id."""

from __future__ import annotations

import argparse

import pytest

from opencontext_cli import main as cli


def test_pin_unknown_id_reports_cleanly(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_agent_memory_store", lambda args: None)
    cli._memory(argparse.Namespace(memory_command="pin", memory_id="nope", config=None))
    assert "not found" in capsys.readouterr().out.lower()


def test_pin_sqlite_record_id_explains_store_mismatch(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    class _Store:
        def get(self, memory_id: str) -> object:
            return object()  # id exists in the SQLite store

    monkeypatch.setattr(cli, "_agent_memory_store", lambda args: _Store())
    cli._memory(argparse.Namespace(memory_command="pin", memory_id="rec-1", config=None))
    out = capsys.readouterr().out
    assert "SQLite" in out and "pin" in out

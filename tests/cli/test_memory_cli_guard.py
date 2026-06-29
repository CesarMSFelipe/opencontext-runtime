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


def test_audit_empty_store_is_clean_not_a_migration_error(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # BUG #2 regression: `memory audit` must audit the live store, never assume a
    # legacy memory.json migration target.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_agent_memory_store", lambda args: None)
    with pytest.raises(SystemExit) as exc:
        cli._memory(argparse.Namespace(memory_command="audit", config=None))
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "memory.json" not in out
    assert "no memory store yet" in out.lower()


def test_audit_reports_live_records(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json
    from datetime import datetime, timedelta

    from opencontext_core.compat import UTC
    from opencontext_core.models.agent_memory import DecayPolicy, MemoryLayer, MemoryRecord

    now = datetime.now(tz=UTC)

    def _rec(rid: str, *, confidence: float, age_days: int) -> MemoryRecord:
        ts = now - timedelta(days=age_days)
        return MemoryRecord(
            id=rid,
            layer=MemoryLayer.SEMANTIC,
            key=f"k:{rid}",
            content=f"durable belief {rid} about the system",
            confidence=confidence,
            decay_policy=DecayPolicy(enabled=False),
            created_at=ts,
            updated_at=ts,
            last_seen_at=ts,
        )

    class _Store:
        def list_records(self, *, limit: int = 200) -> list[MemoryRecord]:
            return [
                _rec("fresh", confidence=0.9, age_days=0),
                _rec("old", confidence=0.2, age_days=200),
            ]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_agent_memory_store", lambda args: _Store())
    with pytest.raises(SystemExit) as exc:
        cli._memory(argparse.Namespace(memory_command="audit", config=None))
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "memory.json" not in out
    report = json.loads(out)
    assert report["total"] == 2
    assert report["stale"]["count"] >= 1
    assert "quality" in report

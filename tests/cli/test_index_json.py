"""``opencontext index --json`` emits a machine-readable report (N1 / AVH-018)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_cli.main import _index, first_party_profiles
from opencontext_core.runtime import OpenContextRuntime


def _runtime() -> OpenContextRuntime:
    return OpenContextRuntime(config_path=None, technology_profiles=first_party_profiles())


def _sample_project(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )


def test_index_json_emits_valid_object_on_success(tmp_path: Path, capsys) -> None:
    _sample_project(tmp_path)
    _index(_runtime(), str(tmp_path), json_output=True)
    out = capsys.readouterr().out.strip()
    report = json.loads(out)  # single, valid JSON object
    assert report["status"] == "ok"
    assert report["error"] is None
    assert isinstance(report["indexed_files"], int)
    assert isinstance(report["symbol_count"], int)
    assert isinstance(report["duration_s"], float)
    assert report["indexed_files"] >= 1


def test_index_json_emits_machine_readable_error(tmp_path: Path, capsys, monkeypatch) -> None:
    runtime = _runtime()
    monkeypatch.setattr(
        runtime, "index_project", lambda *a, **k: (_ for _ in ()).throw(OSError("boom"))
    )
    with pytest.raises(SystemExit) as excinfo:
        _index(runtime, str(tmp_path), json_output=True)
    assert excinfo.value.code == 1
    report = json.loads(capsys.readouterr().out.strip())
    assert report["status"] == "error"
    assert "boom" in report["error"]

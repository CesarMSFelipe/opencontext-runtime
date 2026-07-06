"""`opencontext status` exit codes: ready -> 0, partial -> 3, and pure --json output.

Regression: status always exited 0, so scripts could not distinguish a
configured+indexed workspace from a bare directory. The JSON payload now also
carries `canonical_status` and `exit_code` (additive; legacy keys preserved).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def test_status_partial_exits_3_with_pure_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An empty directory has no workspace: partial -> needs_configuration -> exit 3."""
    import opencontext_cli.main as m

    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    monkeypatch.setattr(sys, "argv", ["opencontext", "status", "--json", str(tmp_path)])

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 3
    out = capsys.readouterr().out
    payload = json.loads(out)  # stdout must be a single pure JSON document
    assert payload["status"] == "partial"
    assert payload["canonical_status"] == "needs_configuration"
    assert payload["exit_code"] == 3
    # Backwards-compatible: pre-existing keys survive the additive change.
    for key in ("schema", "project", "config", "index", "git", "hints", "ci_checks", "workspace"):
        assert key in payload


def test_status_ready_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import opencontext_cli.main as m

    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    (tmp_path / "opencontext.yaml").write_text("project:\n  name: demo\n", encoding="utf-8")
    manifest = tmp_path / ".storage" / "opencontext" / "project_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"files": [], "symbols": []}), encoding="utf-8")

    rc = m._status(str(tmp_path), json_output=True)

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    assert payload["canonical_status"] == "passed"
    assert payload["exit_code"] == 0


def test_status_partial_exits_3_human_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import opencontext_cli.main as m

    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    monkeypatch.setattr(sys, "argv", ["opencontext", "status", str(tmp_path)])

    with pytest.raises(SystemExit) as exc:
        m.main()

    assert exc.value.code == 3
    capsys.readouterr()

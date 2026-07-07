"""OC-004 — `opencontext run` without required configuration returns canonical
``needs_configuration`` (exit 3), never a generic failure, and the report names
the configuration that must be fixed (RUN_STATE_CONTRACT / DOC1 §10).

Uses the in-process pattern of ``tests/cli/test_run_exit_codes.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from opencontext_cli.commands.run_cmd import handle_run_exec


def _args(tmp_path: Path, task: str) -> SimpleNamespace:
    return SimpleNamespace(
        task=task,
        workflow="oc-flow",
        lane="fast",
        profile="balanced",
        root=str(tmp_path),
        config=None,
        json=True,
        yes=True,
        non_interactive=True,
        resume=None,
    )


def _seed_workspace(tmp_path: Path, config_text: str) -> None:
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "opencontext.yaml").write_text(config_text, encoding="utf-8")


def _run_and_parse(tmp_path: Path, monkeypatch, capsys) -> tuple[int, dict]:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    monkeypatch.delenv("OPENCONTEXT_TDD_MODE", raising=False)
    rc = handle_run_exec(_args(tmp_path, "fix the bug in add"))
    out = capsys.readouterr().out
    return rc, json.loads(out)


def test_run_with_unparseable_config_reports_needs_configuration(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """OC-004 — a workspace whose opencontext.yaml cannot be parsed terminates the
    run as canonical needs_configuration with exit code 3, and the message names
    the file to configure (never a generic OPERATION_FAILED envelope)."""
    _seed_workspace(tmp_path, "project: [unclosed\n  bad yaml ::\n")
    rc, payload = _run_and_parse(tmp_path, monkeypatch, capsys)
    assert rc == 3, "needs_configuration must exit 3 (RUN_STATE_CONTRACT)"
    assert payload["status"] == "needs_configuration"
    assert payload["canonical_status"] == "needs_configuration"
    assert payload["exit_code"] == 3
    assert "opencontext.yaml" in str(payload.get("completion_reason", "")), (
        "the report must name the configuration that needs fixing"
    )


def test_run_with_malformed_config_section_reports_needs_configuration(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """OC-004 — a parseable config whose declared section is schema-invalid (a
    malformed storage mode) also terminates canonical needs_configuration,
    exit 3."""
    _seed_workspace(tmp_path, "project:\n  name: demo\nstorage:\n  mode: not-a-real-mode\n")
    rc, payload = _run_and_parse(tmp_path, monkeypatch, capsys)
    assert rc == 3
    assert payload["canonical_status"] == "needs_configuration"


def test_needs_configuration_run_persists_canonical_evidence(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """OC-004 — the needs_configuration terminal persists run.json evidence with
    the canonical state and a failed config_valid gate (RUN_STATE_CONTRACT
    evidence rule)."""
    _seed_workspace(tmp_path, "project: [unclosed\n  bad yaml ::\n")
    rc, _payload = _run_and_parse(tmp_path, monkeypatch, capsys)
    assert rc == 3
    manifests = sorted(tmp_path.glob(".opencontext/sessions/*/runs/*/run.json"))
    assert manifests, "a needs_configuration run must persist run.json evidence"
    manifest = json.loads(manifests[-1].read_text(encoding="utf-8"))
    assert manifest["canonical_status"] == "needs_configuration"
    assert manifest["exit_code"] == 3
    gates_path = manifests[-1].parent / "gates.json"
    gates = json.loads(gates_path.read_text(encoding="utf-8"))["gates"]
    config_gate = next(g for g in gates if g["id"] == "config_valid")
    assert config_gate["status"] == "failed"

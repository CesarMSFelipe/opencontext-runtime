"""PR-013 CLI-CONV: maturity assess smoke + decision-log alias."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from opencontext_cli.commands.maturity_cmd import handle_maturity


def test_maturity_assess_reports_dimensions(tmp_path: Path, capsys) -> None:
    handle_maturity(
        SimpleNamespace(maturity_command="assess", root=str(tmp_path), json=True, output="json")
    )
    data = json.loads(capsys.readouterr().out)
    dims = {d["dimension"] for d in data["dimensions"]}
    assert dims == {"config", "knowledge_graph", "memory", "harness", "benchmark"}
    assert data["overall_level"] in {"none", "basic", "ready"}
    assert data["next_action"]


def test_maturity_human_output(tmp_path: Path, capsys) -> None:
    handle_maturity(
        SimpleNamespace(maturity_command="assess", root=str(tmp_path), json=False, output=None)
    )
    text = capsys.readouterr().out
    assert "Maturity:" in text
    assert "Next:" in text

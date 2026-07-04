"""`runs show`/`runs artifacts` surface OC Flow runs (nested artifact tree).

Regression: OC Flow writes artifacts under artifacts/oc-flow/, so `runs show`
reported artifacts:0 and `runs artifacts` omitted the whole tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.runner import OCFlowRunner


def _run(tmp_path: Path) -> str:
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    edit = ApplyEdit(
        path="calc.py",
        operation=ApplyOperation.REPLACE_RANGE,
        start_line=2,
        end_line=2,
        content="    return a + b",
        reason="fix",
        requirement_refs=["s"],
    )
    result = OCFlowRunner(root=tmp_path).run("fix add", lane=Lane.FAST, requested_edits=[edit])
    return str(result.run_id)


def test_runs_show_counts_ocflow_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    from opencontext_cli.commands.run_cmd import handle_run_inspect

    run_id = _run(tmp_path)
    handle_run_inspect(
        SimpleNamespace(
            runs_action="show", run_id=run_id, root=str(tmp_path), json=True, profile=False
        )
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["artifacts"] > 0, "runs show blind to oc-flow artifacts"


def test_runs_artifacts_includes_ocflow_tree(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    from opencontext_cli.commands.run_cmd import handle_run_inspect

    run_id = _run(tmp_path)
    handle_run_inspect(
        SimpleNamespace(runs_action="artifacts", run_id=run_id, root=str(tmp_path), json=True)
    )
    names = json.loads(capsys.readouterr().out)
    assert any("oc-flow" in n for n in names), "runs artifacts omits the oc-flow tree"

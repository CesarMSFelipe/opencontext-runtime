"""PR-013 SPEC-CLI-013-07/08: top-level run is live; simulate mutates nothing."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from opencontext_cli.commands.run_cmd import handle_simulate


def test_run_is_not_deprecated() -> None:
    from opencontext_cli.main import _DeprecationAwareParser

    assert "run" not in _DeprecationAwareParser._DEPRECATED


def test_simulate_previews_without_mutation(tmp_path: Path, capsys) -> None:
    args = SimpleNamespace(
        task="add a unit test for parser", root=str(tmp_path), json=True, output="json"
    )
    before = set(tmp_path.rglob("*"))
    handle_simulate(args)
    after = set(tmp_path.rglob("*"))
    assert before == after, "simulate must not create or modify files"

    out = json.loads(capsys.readouterr().out)
    assert out["mutated"] is False
    assert out["provider_calls"] == 0
    assert out["workflow"]
    assert isinstance(out["policy_decisions"], list) and out["policy_decisions"]


def test_simulate_human_output(tmp_path: Path, capsys) -> None:
    args = SimpleNamespace(task="fix bug", root=str(tmp_path), json=False, output=None)
    handle_simulate(args)
    text = capsys.readouterr().out
    assert "Workflow" in text
    assert "dry run" in text.lower()

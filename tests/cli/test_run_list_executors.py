"""`opencontext run --list-executors --json` lists the executor registry.

The formal executor registry (EXE tests) must be visible from the CLI so a
user/CI can see which executors exist and what each is allowed to do.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from opencontext_cli.commands.run_cmd import handle_run_exec


def _args(tmp_path: Path, *, as_json: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        task=None,
        workflow="oc-flow",
        lane="fast",
        profile="balanced",
        root=str(tmp_path),
        config=None,
        json=as_json,
        yes=True,
        non_interactive=True,
        resume=None,
        list_executors=True,
    )


def test_list_executors_json_shape(tmp_path: Path, capsys) -> None:
    rc = handle_run_exec(_args(tmp_path))
    out = capsys.readouterr().out
    assert rc == 0
    data = json.loads(out)
    executors = {spec["id"]: spec for spec in data["executors"]}
    assert {"none", "provider", "mcp", "test_stub", "patch"} <= set(executors)
    for spec in executors.values():
        for key in (
            "id",
            "description",
            "can_mutate",
            "can_run_commands",
            "requires_network",
            "requires_approval",
            "supported_tasks",
            "supported_languages",
        ):
            assert key in spec
    assert executors["patch"]["can_mutate"] is True
    assert executors["patch"]["can_run_commands"] is False
    assert executors["none"]["can_mutate"] is False


def test_list_executors_human_output(tmp_path: Path, capsys) -> None:
    rc = handle_run_exec(_args(tmp_path, as_json=False))
    out = capsys.readouterr().out
    assert rc == 0
    assert "patch" in out

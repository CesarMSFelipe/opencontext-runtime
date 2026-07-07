"""KG-CMDS: `knowledge-graph callers` / `callees` CLI subcommands work end-to-end.

Drives the real parser + handle_kg dispatch against an indexed project and
asserts pure, parseable JSON output (CLI_CONTRACT JSON purity rule).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import opencontext_cli.main as cli_main
from opencontext_cli.commands.kg_cmd import handle_kg
from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    (tmp_path / "mod.py").write_text(
        "def helper():\n    return 1\n\n\ndef runner():\n    return helper()\n",
        encoding="utf-8",
    )
    kg = KnowledgeGraph(
        config=KnowledgeGraphConfig(enabled=True, languages=["python"]),
        db_path=tmp_path / ".storage" / "opencontext" / "context_graph.db",
    )
    kg.index_project(tmp_path)
    kg.close()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_parser_accepts_callers_and_callees_flags() -> None:
    """KG-CMDS: parser wires the callers/callees subcommands with --depth/--json."""
    callers = cli_main._build_parser().parse_args(
        ["knowledge-graph", "callers", "helper", "--depth", "3", "--json"]
    )
    assert callers.kg_command == "callers"
    assert callers.symbol == "helper"
    assert callers.depth == 3
    assert callers.json is True
    callees = cli_main._build_parser().parse_args(["knowledge-graph", "callees", "runner"])
    assert callees.kg_command == "callees"
    assert callees.symbol == "runner"


def test_callers_json_lists_calling_symbols(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """KG-CMDS: `knowledge-graph callers --json` emits the calling symbols as pure JSON."""
    args = cli_main._build_parser().parse_args(["knowledge-graph", "callers", "helper", "--json"])
    handle_kg(args)
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert "runner" in {entry["name"] for entry in payload}


def test_callees_json_lists_called_symbols(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """KG-CMDS: `knowledge-graph callees --json` emits the called symbols as pure JSON."""
    args = cli_main._build_parser().parse_args(["knowledge-graph", "callees", "runner", "--json"])
    handle_kg(args)
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert "helper" in {entry["name"] for entry in payload}

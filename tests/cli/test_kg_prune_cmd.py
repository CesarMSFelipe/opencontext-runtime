"""`knowledge-graph prune` CLI: drop graph entries for files deleted from disk."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import opencontext_cli.main as cli_main
from opencontext_cli.commands.kg_cmd import handle_kg
from opencontext_core.config import KnowledgeGraphConfig
from opencontext_core.indexing.knowledge_graph import KnowledgeGraph


def _index_project(root: Path) -> None:
    (root / "keeper.py").write_text("def kept():\n    return 1\n", encoding="utf-8")
    (root / "goner.py").write_text("def gone():\n    return 2\n", encoding="utf-8")
    kg = KnowledgeGraph(
        config=KnowledgeGraphConfig(enabled=True, languages=["python"]),
        db_path=root / ".storage" / "opencontext" / "context_graph.db",
    )
    kg.index_project(root)
    kg.close()


def test_parser_accepts_prune_flags() -> None:
    args = cli_main._build_parser().parse_args(["knowledge-graph", "prune", "--dry-run", "--json"])
    assert args.kg_command == "prune"
    assert args.dry_run is True
    assert args.json is True


def test_prune_json_reports_removals(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    _index_project(tmp_path)
    (tmp_path / "goner.py").unlink()
    args = cli_main._build_parser().parse_args(
        ["knowledge-graph", "prune", "--root", str(tmp_path), "--json"]
    )
    handle_kg(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is False
    assert payload["nodes_removed"] == 1
    assert payload["edges_removed"] >= 0


def test_prune_dry_run_leaves_graph_intact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    _index_project(tmp_path)
    (tmp_path / "goner.py").unlink()
    args = cli_main._build_parser().parse_args(
        ["knowledge-graph", "prune", "--root", str(tmp_path), "--dry-run", "--json"]
    )
    handle_kg(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["nodes_removed"] == 1
    # A second dry-run still sees the stale node — nothing was deleted.
    handle_kg(
        cli_main._build_parser().parse_args(
            ["knowledge-graph", "prune", "--root", str(tmp_path), "--dry-run", "--json"]
        )
    )
    payload_again = json.loads(capsys.readouterr().out)
    assert payload_again["nodes_removed"] == 1

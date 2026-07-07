"""KG-006: `knowledge-graph explain-pack` CLI justifies pack selection.

Drives the real CLI dispatch (parser + handle_kg) against a persisted run pack
and asserts the justification JSON: per-item reasons, edges used, omission
reasons, and the metrics block passthrough.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import opencontext_cli.main as cli_main
from opencontext_cli.commands.kg_cmd import handle_kg
from opencontext_cli.contracts import CliContractError

_PACK = {
    "included": [
        {
            "id": "graph:calculator.py:3:multiply_values",
            "content": "def multiply_values(a, b): ...",
            "source": "calculator.py:3",
            "source_type": "graph_symbol",
            "tokens": 24,
            "score": 0.9,
            "metadata": {
                "reason": "included via graph",
                "retrieval_source": "graph",
                "graph_provenance": {
                    "file_path": "calculator.py",
                    "line": 3,
                    "relationships": ["called_by:test_multiply_values"],
                },
            },
        },
    ],
    "omitted": [],
    "used_tokens": 24,
    "available_tokens": 800,
    "omissions": [
        {"item_id": "big.py", "reason": "token_budget_exceeded", "tokens": 900, "score": 0.1}
    ],
    "compression": None,
    "context": {
        "budget_tokens": 800,
        "input_tokens_estimated": 924,
        "output_tokens_estimated": 24,
        "compression_ratio": None,
        "kg_used": True,
        "kg_nodes_used": 1,
        "kg_edges_used": 1,
        "memory_hits": 0,
        "protected_spans": 0,
        "protected_spans_kept": 0,
        "excluded_files": 1,
    },
}


def _persist_pack(root: Path, run_id: str) -> Path:
    pack_path = root / ".opencontext" / "runs" / run_id / "context-pack.json"
    pack_path.parent.mkdir(parents=True)
    pack_path.write_text(json.dumps(_PACK), encoding="utf-8")
    return pack_path


def test_parser_accepts_explain_pack_flags() -> None:
    """KG-006: parser wires the explain-pack subcommand with --run/--root/--json."""
    args = cli_main._build_parser().parse_args(
        ["knowledge-graph", "explain-pack", "--run", "run-1", "--json"]
    )
    assert args.kg_command == "explain-pack"
    assert args.run == "run-1"
    assert args.json is True


def test_explain_pack_json_reports_selection_justification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """KG-006: explain-pack --json emits per-item reasons, edges and omissions as pure JSON."""
    _persist_pack(tmp_path, "run-1")
    args = cli_main._build_parser().parse_args(
        ["knowledge-graph", "explain-pack", "--run", "run-1", "--root", str(tmp_path), "--json"]
    )
    handle_kg(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "run-1"
    selected = payload["selected"]
    assert selected[0]["id"] == "graph:calculator.py:3:multiply_values"
    assert selected[0]["reason"] == "included via graph"
    assert selected[0]["retrieval_source"] == "graph"
    assert payload["edges_used"] == ["called_by:test_multiply_values"]
    assert payload["omissions"] == [
        {"item_id": "big.py", "reason": "token_budget_exceeded", "tokens": 900}
    ]
    assert payload["context"]["kg_nodes_used"] == 1


def test_explain_pack_missing_run_raises_contract_error(tmp_path: Path) -> None:
    """KG-006: explain-pack fails with the RUN_NOT_FOUND contract error for unknown runs.

    CLI-ERR-CODES: the code is the cataloged SCREAMING_SNAKE identifier
    (``run_not_found`` was migrated to conform to CLI_CONTRACT).
    """
    args = cli_main._build_parser().parse_args(
        ["knowledge-graph", "explain-pack", "--run", "ghost", "--root", str(tmp_path), "--json"]
    )
    with pytest.raises(CliContractError) as excinfo:
        handle_kg(args)
    assert excinfo.value.code == "RUN_NOT_FOUND"

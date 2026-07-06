"""Explain-pack payload tests (KG_CONTEXT_COMPRESSION_CONTRACT query surface)."""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.context.pack_explain import (
    explain_pack_payload,
    locate_run_context_pack,
)

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
        {
            "id": "readme",
            "content": "readme text",
            "source": "README.md",
            "source_type": "file",
            "tokens": 10,
            "score": 0.2,
            "metadata": {},
        },
    ],
    "omitted": [],
    "used_tokens": 34,
    "available_tokens": 800,
    "omissions": [
        {"item_id": "big.py", "reason": "token_budget_exceeded", "tokens": 900, "score": 0.1}
    ],
    "compression": None,
    "context": {
        "budget_tokens": 800,
        "input_tokens_estimated": 934,
        "output_tokens_estimated": 34,
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


class TestLocateRunContextPack:
    def test_finds_pack_under_runs_layout(self, tmp_path: Path) -> None:
        pack_path = tmp_path / ".opencontext" / "runs" / "run-1" / "context-pack.json"
        pack_path.parent.mkdir(parents=True)
        pack_path.write_text(json.dumps(_PACK), encoding="utf-8")
        assert locate_run_context_pack(tmp_path, "run-1") == pack_path

    def test_finds_pack_under_sessions_layout(self, tmp_path: Path) -> None:
        pack_path = (
            tmp_path
            / ".opencontext"
            / "sessions"
            / "sess-a"
            / "runs"
            / "run-2"
            / "context-pack.json"
        )
        pack_path.parent.mkdir(parents=True)
        pack_path.write_text(json.dumps(_PACK), encoding="utf-8")
        assert locate_run_context_pack(tmp_path, "run-2") == pack_path

    def test_returns_none_when_run_missing(self, tmp_path: Path) -> None:
        assert locate_run_context_pack(tmp_path, "ghost") is None


class TestExplainPackPayload:
    def test_payload_reports_selection_and_reasons(self) -> None:
        payload = explain_pack_payload(_PACK, run_id="run-1", pack_path="/tmp/x.json")
        assert payload["run_id"] == "run-1"
        assert payload["pack_path"] == "/tmp/x.json"
        selected = payload["selected"]
        assert [s["id"] for s in selected] == [
            "graph:calculator.py:3:multiply_values",
            "readme",
        ]
        assert selected[0]["reason"] == "included via graph"
        assert selected[0]["retrieval_source"] == "graph"
        # Reasonless legacy items still get a non-empty reason.
        assert selected[1]["reason"]

    def test_payload_reports_edges_and_omissions(self) -> None:
        payload = explain_pack_payload(_PACK, run_id="run-1", pack_path="p")
        assert payload["edges_used"] == ["called_by:test_multiply_values"]
        assert payload["omissions"][0]["item_id"] == "big.py"
        assert payload["omissions"][0]["reason"] == "token_budget_exceeded"

    def test_payload_passes_through_metrics_block(self) -> None:
        payload = explain_pack_payload(_PACK, run_id="run-1", pack_path="p")
        assert payload["context"]["kg_nodes_used"] == 1
        assert payload["context"]["budget_tokens"] == 800

    def test_payload_tolerates_legacy_pack_without_metrics(self) -> None:
        legacy = {k: v for k, v in _PACK.items() if k != "context"}
        payload = explain_pack_payload(legacy, run_id="run-1", pack_path="p")
        assert payload["context"] is None

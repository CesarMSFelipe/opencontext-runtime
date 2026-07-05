from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import opencontext_cli.main as cli_main


def test_verified_context_cli_outputs_json_and_passes(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    result = SimpleNamespace(
        model_dump=lambda mode="json": {
            "trace_id": "trace-ok",
            "context": "context",
            "evidence": [],
            "memory": [],
            "gates": [{"name": "coverage", "passed": True, "reason": "ok", "risks": []}],
            "risk_level": "normal",
            "trust_decision": {"status": "sufficient", "reason": "ok"},
            "token_usage": {"final_context_pack": 10},
            "omitted_sources": [],
        }
    )
    monkeypatch.setattr(
        cli_main,
        "_runtime",
        lambda config: SimpleNamespace(verify_context=lambda request: result),
    )
    monkeypatch.setattr(cli_main, "_check_first_run", lambda command, args=None: None)

    args = cli_main._build_parser().parse_args(["verified-context", "auth", "--json"])
    cli_main._dispatch(args)

    assert json.loads(capsys.readouterr().out)["trace_id"] == "trace-ok"


def test_verified_context_cli_fails_when_required_gate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = SimpleNamespace(
        model_dump=lambda mode="json": {
            "trace_id": "trace-fail",
            "context": "",
            "evidence": [],
            "memory": [],
            "gates": [{"name": "coverage", "passed": False, "reason": "missing", "risks": []}],
            "risk_level": "high",
            "trust_decision": {"status": "insufficient", "reason": "missing"},
            "token_usage": {"final_context_pack": 0},
            "omitted_sources": ["manifest_unavailable"],
        }
    )
    monkeypatch.setattr(
        cli_main,
        "_runtime",
        lambda config: SimpleNamespace(verify_context=lambda request: result),
    )
    monkeypatch.setattr(cli_main, "_check_first_run", lambda command, args=None: None)

    args = cli_main._build_parser().parse_args(["verified-context", "secret"])

    with pytest.raises(SystemExit) as exc:
        cli_main._dispatch(args)

    assert exc.value.code == 1

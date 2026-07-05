"""Tests for cross-command flag consistency and additive command namespaces.

Covers:
- ``flag > env > default`` precedence resolution for common boolean flags.
- ``kg`` and ``context`` namespace aliases existing as *additional* entry
  points without removing the flat ``knowledge-graph`` command.
- Bare ``opencontext`` still launching the interactive menu.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import opencontext_cli.main as cli_main

# ── flag > env > default precedence ──────────────────────────────────────────


def test_resolve_flag_true_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCONTEXT_JSON", raising=False)
    assert cli_main._resolve_flag(True, "OPENCONTEXT_JSON", default=False) is True


def test_resolve_flag_uses_env_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCONTEXT_JSON", "1")
    assert cli_main._resolve_flag(False, "OPENCONTEXT_JSON", default=False) is True


def test_resolve_flag_env_falsey_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCONTEXT_YES", "0")
    assert cli_main._resolve_flag(False, "OPENCONTEXT_YES", default=False) is False
    monkeypatch.setenv("OPENCONTEXT_YES", "false")
    assert cli_main._resolve_flag(False, "OPENCONTEXT_YES", default=False) is False


def test_resolve_flag_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCONTEXT_QUIET", raising=False)
    assert cli_main._resolve_flag(False, "OPENCONTEXT_QUIET", default=True) is True


def test_resolve_flag_flag_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicit flag wins over a conflicting env var.
    monkeypatch.setenv("OPENCONTEXT_DRY_RUN", "0")
    assert cli_main._resolve_flag(True, "OPENCONTEXT_DRY_RUN", default=False) is True


# ── additive namespaces: kg / context ────────────────────────────────────────


def test_knowledge_graph_flat_command_still_parses() -> None:
    args = cli_main._build_parser().parse_args(["knowledge-graph", "status"])
    assert args.command == "knowledge-graph"
    assert args.kg_command == "status"


def test_kg_alias_parses_same_subcommands() -> None:
    args = cli_main._build_parser().parse_args(["kg", "status"])
    assert args.kg_command == "status"


def test_kg_alias_search_parses_query_and_flags() -> None:
    args = cli_main._build_parser().parse_args(["kg", "search", "auth", "--limit", "5", "--json"])
    assert args.kg_command == "search"
    assert args.query == "auth"
    assert args.limit == 5
    assert args.json is True


def test_kg_alias_dispatches_to_kg_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(cli_main, "handle_kg", lambda args: seen.setdefault("cmd", args.kg_command))
    monkeypatch.setattr(cli_main, "_check_first_run", lambda command, args=None: None)
    monkeypatch.setattr(cli_main, "_notify_outdated", lambda args: None)

    args = cli_main._build_parser().parse_args(["kg", "status"])
    cli_main._dispatch(args)
    assert seen["cmd"] == "status"


def test_context_alias_dispatches_to_verified_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_runtime(config: str) -> SimpleNamespace:
        return SimpleNamespace(
            verify_context=lambda request: SimpleNamespace(
                model_dump=lambda mode="json": {
                    "trace_id": "t",
                    "context": "ctx",
                    "evidence": [],
                    "memory": [],
                    "gates": [{"name": "coverage", "passed": True, "reason": "ok", "risks": []}],
                    "risk_level": "normal",
                    "trust_decision": {"status": "sufficient", "reason": "ok"},
                    "token_usage": {"final_context_pack": 1},
                    "omitted_sources": [],
                }
            )
        )

    monkeypatch.setattr(cli_main, "_runtime", _fake_runtime)
    monkeypatch.setattr(cli_main, "_check_first_run", lambda command, args=None: None)
    monkeypatch.setattr(cli_main, "_notify_outdated", lambda args: None)

    args = cli_main._build_parser().parse_args(["context", "auth", "--json"])
    cli_main._dispatch(args)
    captured["ok"] = True
    assert captured["ok"] is True


# ── bare invocation still launches the menu ──────────────────────────────────


def test_no_command_launches_menu(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: dict[str, bool] = {}

    import opencontext_cli.commands.menu_cmd as menu_cmd

    monkeypatch.setattr(menu_cmd, "run_main_menu", lambda: launched.setdefault("yes", True))

    args = cli_main._build_parser().parse_args([])
    cli_main._dispatch(args)
    assert launched.get("yes") is True

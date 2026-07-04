"""P1.3 -- machine-readable --json for status, install, memory init,
memory list, explain, and config show.

Each test:
  1. Passes ``--json`` (or json_output=True) to the relevant handler
  2. Asserts that stdout is parseable JSON
  3. Asserts expected stable keys are present
  4. Asserts exit code 0 (or no abnormal SystemExit)
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_runtime(tmp_path: Path) -> Any:
    """Minimal runtime double backed by a real temp directory."""
    from opencontext_cli.main import first_party_profiles
    from opencontext_core.runtime import OpenContextRuntime

    return OpenContextRuntime(config_path=None, technology_profiles=first_party_profiles())


# ---------------------------------------------------------------------------
# 1. status --json
# ---------------------------------------------------------------------------


def test_status_json_emits_valid_object(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencontext status --json must emit a single valid JSON object."""
    import opencontext_cli.main as cli_main

    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    cli_main._status(str(tmp_path), json_output=True)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert "schema" in data
    assert "project" in data
    assert "status" in data


# ---------------------------------------------------------------------------
# 2. install --json
# ---------------------------------------------------------------------------


def test_install_json_emits_valid_object(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencontext install --json must emit a single valid JSON object and exit 0."""
    import opencontext_cli.main as cli_main

    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

    args = SimpleNamespace(
        root=str(tmp_path),
        yes=True,
        agent=None,
        flow="oc-new",
        tdd=None,
        preset=None,
        memory_mode=None,
        install_engram=False,
        openspec_mode=None,
        dry_run=False,
        json=True,
    )
    cli_main._install(args)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert "schema" in data
    assert "status" in data


# ---------------------------------------------------------------------------
# 3. memory init --json
# ---------------------------------------------------------------------------


def test_memory_init_json_emits_valid_object(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencontext memory init --json must emit a single valid JSON object."""
    import opencontext_cli.main as cli_main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

    args = SimpleNamespace(memory_command="init", json=True)
    cli_main._memory(args)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert "schema" in data
    assert "status" in data
    assert "created" in data


# ---------------------------------------------------------------------------
# 4. memory list --json
# ---------------------------------------------------------------------------


def test_memory_list_json_emits_valid_object(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencontext memory list --json must emit a single valid JSON object."""
    import opencontext_cli.main as cli_main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")

    args = SimpleNamespace(memory_command="list", json=True)
    cli_main._memory(args)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert "schema" in data
    assert "records" in data
    assert isinstance(data["records"], list)


# ---------------------------------------------------------------------------
# 5. explain --json
# ---------------------------------------------------------------------------


def test_explain_json_emits_valid_object(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencontext explain <query> --json must emit a single valid JSON object."""
    from opencontext_cli.commands.explain_cmd import handle_explain

    # Minimal stub runtime that returns a pack with no items.
    pack = SimpleNamespace(
        included=[],
        omitted=[],
        omissions=[],
        used_tokens=0,
    )
    runtime = SimpleNamespace(
        build_context_pack=lambda q, max_tok: pack,
        index_project=lambda root: None,
        knowledge_graph=SimpleNamespace(stale_files=lambda r: SimpleNamespace(total=0)),
    )
    args = SimpleNamespace(
        query="fix the auth bug",
        root=".",
        max_tokens=None,
        breakdown=False,
        why=None,
        json=True,
    )
    rc = handle_explain(runtime, args)
    assert rc == 0
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert "schema" in data
    assert "query" in data
    assert "included" in data


# ---------------------------------------------------------------------------
# 6. config show --json
# ---------------------------------------------------------------------------


def test_config_show_json_emits_valid_object(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencontext config show --json must emit a single valid JSON object."""
    from opencontext_cli.commands.config_cmd import handle_config

    monkeypatch.chdir(tmp_path)
    args = SimpleNamespace(
        config_command="show",
        root=str(tmp_path),
        json=True,
    )
    handle_config(args)
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert "schema" in data
    assert "security_mode" in data
    assert "features" in data

from __future__ import annotations

import json
from pathlib import Path

from opencontext_cli.main import (
    _agent_context,
    _checkpoint,
    _doctor,
    _eval,
    _init,
    _pack,
    _pack_diff,
    _provider_simulate,
    _security,
    _tokens,
    _workflows,
)
from opencontext_core.runtime import OpenContextRuntime
from tests.core.conftest import write_config


def test_check_deprecation() -> None:
    """check command is now in _DEPRECATED frozenset — it exits 2 via _DeprecationAwareParser."""
    from opencontext_cli.main import _DeprecationAwareParser

    assert "check" in _DeprecationAwareParser._DEPRECATED


def test_checkpoint_create_outputs_hashes(capsys) -> None:
    _checkpoint("create")
    output = capsys.readouterr().out
    data = json.loads(output)
    assert "project_hash" in data
    assert data["trace_id"] == "scaffold-trace"


def test_security_scan_outputs_warning(capsys) -> None:
    _security("scan")
    out = capsys.readouterr().out
    # Output is now human-readable (not JSON)
    assert "Secret values are redacted" in out or "finding" in out.lower() or "No secret" in out


def test_pack_diff_scaffold(capsys) -> None:
    _pack_diff("main", "HEAD")
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "scaffold"


def test_eval_run_handles_missing_path(capsys) -> None:
    """eval run with no path prints a helpful message."""
    runtime = OpenContextRuntime()
    _eval(runtime, "run", None, ".", 6000, 0.5)
    out = capsys.readouterr().out
    assert "eval file" in out.lower() or "no eval" in out.lower() or "path" in out.lower()


def test_tokens_report(capsys) -> None:
    _tokens("report")
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"


def test_agent_context_copy_fallback(capsys) -> None:
    _agent_context("review auth", "plan", 1000, copy=True)
    out = capsys.readouterr().out
    assert "Agent Context" in out


def test_doctor_tokens_suggest_ignore(tmp_path: Path, capsys) -> None:
    from opencontext_core.runtime import OpenContextRuntime

    runtime = OpenContextRuntime(storage_path=tmp_path / ".storage/opencontext")
    _doctor(runtime, "tokens", suggest_ignore=True)
    output = capsys.readouterr().out
    assert "Token report" in output or "tokens" in output.lower()


def test_init_template_creates_workspace_and_config(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _init("opencontext.yaml", "enterprise")
    out = capsys.readouterr().out
    assert "Template: enterprise" in out
    assert (tmp_path / "opencontext.yaml").exists()
    assert (tmp_path / ".opencontext/policies/security-policy.yaml").exists()


def test_init_profile_writes_canonical_config(tmp_path: Path, monkeypatch, capsys) -> None:
    """`init --profile <name>` sets the config profile at <root>/opencontext.yaml."""
    import yaml

    from opencontext_core.config import load_config

    monkeypatch.chdir(tmp_path)
    # Use a non-default profile so the assertion proves the flag was honoured
    # (``balanced`` is the OpenContextConfig default).
    _init("opencontext.yaml", non_interactive=True, profile="research")
    out = capsys.readouterr().out
    assert "Profile: research" in out

    cfg = tmp_path / "opencontext.yaml"
    assert cfg.exists()
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert raw["profile"] == "research"
    # Loads cleanly via the strict OpenContextConfig model (extra="forbid").
    assert load_config(cfg).profile == "research"


def test_init_profile_balanced_non_interactive(tmp_path: Path, monkeypatch) -> None:
    """The documented 1.0 DoD sequence: `init --profile balanced --non-interactive`."""
    from opencontext_core.config import load_config

    monkeypatch.chdir(tmp_path)
    _init("opencontext.yaml", non_interactive=True, profile="balanced")
    cfg = tmp_path / "opencontext.yaml"
    assert cfg.exists()
    assert load_config(cfg).profile == "balanced"


def test_more_required_scaffolds(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "workflow-packs/example").mkdir(parents=True)
    (tmp_path / "workflow-packs/example/workflow.yaml").write_text("name: example\n")

    _workflows("list", None)
    assert json.loads(capsys.readouterr().out) == ["example"]
    _workflows("inspect", "example")
    assert json.loads(capsys.readouterr().out)["status"] == "available"


def test_provider_simulate_denies_confidential(tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config_path = write_config(tmp_path, project)
    runtime = OpenContextRuntime(config_path=config_path, storage_path=tmp_path / ".storage")

    _provider_simulate("openai", "confidential", runtime)
    provider = json.loads(capsys.readouterr().out)
    assert provider["decision"]["allowed"] is False


def test_pack_output_file_is_redacted(tmp_path: Path, capsys) -> None:
    project = tmp_path / "project"
    project.mkdir()
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    (project / "auth.py").write_text(f"API_KEY = '{secret}'\n", encoding="utf-8")
    config_path = write_config(tmp_path, project)
    runtime = OpenContextRuntime(config_path=config_path, storage_path=tmp_path / ".storage")
    runtime.index_project(project)
    output = tmp_path / ".opencontext/context-packs/auth.md"

    # Root the pack at the tmp project: ``_pack`` records a telemetry event under
    # ``<root>/.opencontext/telemetry/events.jsonl`` and ``root`` defaults to
    # ``"."`` (the process CWD == this repo). Under the parallel unit lane that
    # append races the snapshot guards in ``test_ci_quality_checks.py`` /
    # ``test_quality_gate.py``. Passing the tmp project keeps the write hermetic.
    _pack(runtime, "API_KEY", 2000, "markdown", "audit", False, str(output), root=str(project))

    assert "Wrote context pack" in capsys.readouterr().out
    rendered = output.read_text(encoding="utf-8")
    assert secret not in rendered
    assert "Security Warnings" in rendered

"""OC-STATES — producers for the remaining OC Flow run-level canonical states
(DOC1 §10 / RUN_STATE_CONTRACT): ``needs_approval`` when policy demands human
approval before a write, and ``needs_context`` when the flow cannot build
sufficient context for the task.

Uses the in-process pattern of ``tests/cli/test_run_exit_codes.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from opencontext_cli.commands.run_cmd import handle_run_exec

BUGGY = "def add(a, b):\n    return a - b\n"


def _args(tmp_path: Path, task: str) -> SimpleNamespace:
    return SimpleNamespace(
        task=task,
        workflow="oc-flow",
        lane="fast",
        profile="balanced",
        root=str(tmp_path),
        config=None,
        json=True,
        yes=True,
        non_interactive=True,
        resume=None,
    )


def test_policy_approval_required_reports_needs_approval(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """OC-STATES — when policy requires human approval for writes
    (policies.writes.require_approval), the run surfaces the policy-gate outcome
    as canonical needs_approval with exit code 4 and applies NO edit."""
    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    monkeypatch.delenv("OPENCONTEXT_TDD_MODE", raising=False)
    (tmp_path / "calc.py").write_text(BUGGY, encoding="utf-8")
    edits = [
        {
            "path": "calc.py",
            "operation": "replace_range",
            "start_line": 1,
            "end_line": 2,
            "content": "def add(a, b):\n    return a + b\n",
            "reason": "fix the add bug",
            "requirement_refs": ["task addressed"],
        }
    ]
    (tmp_path / "provider_stub.json").write_text(json.dumps(edits), encoding="utf-8")
    (tmp_path / "opencontext.yaml").write_text(
        "provider: test_stub\n"
        "edits_file: provider_stub.json\n"
        "policies:\n"
        "  writes:\n"
        "    require_approval: true\n",
        encoding="utf-8",
    )
    rc = handle_run_exec(_args(tmp_path, "fix the bug in add"))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 4, "needs_approval must exit 4 (RUN_STATE_CONTRACT)"
    assert payload["status"] == "needs_approval"
    assert payload["canonical_status"] == "needs_approval"
    assert payload["legacy_status"] == "policy_blocked"
    assert payload["exit_code"] == 4
    assert "approval" in str(payload.get("completion_reason", "")).lower()
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == BUGGY, (
        "no edit may be applied before approval is granted"
    )


def test_empty_context_envelope_reports_needs_context(tmp_path: Path, monkeypatch, capsys) -> None:
    """OC-STATES — when context gathering cannot produce a single context item,
    the run terminates as canonical needs_context with exit code 1 instead of
    proceeding to plan on nothing."""
    from opencontext_core.oc_flow import nodes as oc_nodes
    from opencontext_core.oc_flow.models import ContextEnvelope

    monkeypatch.setenv("OPENCONTEXT_STORAGE_MODE", "local")
    monkeypatch.delenv("OPENCONTEXT_TDD_MODE", raising=False)
    (tmp_path / "calc.py").write_text(BUGGY, encoding="utf-8")
    monkeypatch.setattr(
        oc_nodes.DeterministicNodeExecutor,
        "gather_context",
        lambda self, task, seed_paths, depth: ContextEnvelope(task=task, items=[]),
    )
    rc = handle_run_exec(_args(tmp_path, "fix the bug in add"))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1, "needs_context must exit 1 (RUN_STATE_CONTRACT)"
    assert payload["status"] == "needs_context"
    assert payload["canonical_status"] == "needs_context"
    assert payload["exit_code"] == 1

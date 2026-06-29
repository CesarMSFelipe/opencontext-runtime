"""PR-013 SPEC-CLI-013-10: workflow explain + profile explain."""

from __future__ import annotations

import json
from types import SimpleNamespace

from opencontext_cli.commands.profile_cmd import handle_profile
from opencontext_cli.commands.ux_cmd import handle_workflow_ux


def test_workflow_explain_sdd(capsys) -> None:
    handle_workflow_ux(
        SimpleNamespace(workflow_command="explain", workflow="sdd", root=None, json_out=True)
    )
    info = json.loads(capsys.readouterr().out)
    assert info["id"] == "sdd"
    assert info["when"]
    assert info["cost"] == "high"
    assert info["phases"]
    assert info["harnesses"]


def test_profile_explain_enterprise(capsys) -> None:
    rc = handle_profile(SimpleNamespace(profile_command="explain", name="enterprise", json=True))
    assert rc == 0
    info = json.loads(capsys.readouterr().out)
    assert info["family"] == "config"
    assert info["security"]["mode"] == "enterprise"
    assert info["approvals"]["approval_required_for_writes"] is True


def test_workflow_explain_unknown_errors(capsys) -> None:
    import pytest

    with pytest.raises(SystemExit):
        handle_workflow_ux(
            SimpleNamespace(
                workflow_command="explain", workflow="nonsense", root=None, json_out=True
            )
        )

"""`run --workflow auto --json` emits a STRUCTURED recommend-SDD handoff (GAP 3).

When auto-selection routes a broad/high-risk task to SDD, the ``--json`` output must
be a valid JSON object that downstream consumers can branch on (``workflow == "sdd"``,
``recommended_command``) — not a human string. The recommend-SDD *behaviour* is
correct (OC Flow hands off to SDD); only the JSON shape is pinned here. The localized
bugfix case must still emit its own valid oc-flow JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontext_core.oc_flow.cli import run_oc_flow_cli

_REDESIGN = "Redesign public API and migrate database schema"
_BUGFIX = "Fix failing test in tests/unit/test_parser.py"


def test_recommend_sdd_summary_is_structured(tmp_path: Path) -> None:
    summary = run_oc_flow_cli(_REDESIGN, root=tmp_path, workflow="auto", enabled=True)
    assert summary["status"] == "recommend_sdd"
    assert summary["workflow"] == "sdd"
    assert summary["recommended_command"] == "opencontext harness run --workflow sdd"
    assert summary["selection_reason"]
    assert summary["message"]


def test_recommend_sdd_json_is_valid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_oc_flow_cli(_REDESIGN, root=tmp_path, workflow="auto", enabled=True, as_json=True)
    payload = json.loads(capsys.readouterr().out)  # raises if not valid JSON
    assert payload["status"] == "recommend_sdd"
    assert payload["workflow"] == "sdd"
    assert payload["recommended_command"] == "opencontext harness run --workflow sdd"


def test_localized_bugfix_json_still_valid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_oc_flow_cli(_BUGFIX, root=tmp_path, workflow="auto", enabled=True, as_json=True)
    payload = json.loads(capsys.readouterr().out)  # raises if not valid JSON
    assert payload["status"] != "recommend_sdd"
    assert payload["workflow"] == "oc-flow"

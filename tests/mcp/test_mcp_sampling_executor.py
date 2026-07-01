"""MCP Sampling ApplyEdit Executor tests (PR-AHE-002).

Covers:
- Task 2.1/2.2: ApplyEdit parsing/validation for replace_range|create_file|delete_file
- Task 2.3: Path validation (no traversal, no absolute paths)
- Task 2.4: Range validation for replace_range
- Task 2.7: Valid sampling edit e2e (golden bug fixed and verified)
- Task 2.8: Malformed sampling response returns blocked, no file mutation
- Task 2.9: Dangerous secret edit creating .env is blocked before apply
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from opencontext_core.agents.executor import ApplyEdit, ApplyOperation
from opencontext_core.llm.sampling_gateway import register_host_sampler
from opencontext_core.oc_flow import cli as oc_flow_cli
from opencontext_core.oc_flow.cli import run_oc_flow_cli
from opencontext_core.oc_flow.nodes import (
    _invalid_edit_contract_reason,
    _parse_apply_edit_set,
    _unsafe_edit_reason,
)
from opencontext_core.providers.detect import DetectedProvider

_GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "oc_flow_bugfix_python"

_VALID_EDIT_JSON = (
    '[{"path":"buggy_add.py","operation":"replace_range","start_line":2,"end_line":2,'
    '"content":"    return a + b","reason":"fix the operator",'
    '"requirement_refs":["add returns the sum"]}]'
)


@pytest.fixture(autouse=True)
def _clear_sampler():
    register_host_sampler(None)
    yield
    register_host_sampler(None)


def _pin_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )


# ------------------------------------------------------------------ 2.2 ApplyEdit parsing


def test_applyedit_valid_replace_range_parses() -> None:
    edits = _parse_apply_edit_set(
        '[{"path":"foo.py","operation":"replace_range","start_line":1,"end_line":2,'
        '"content":"x = 1","reason":"fix","requirement_refs":["r1"]}]'
    )
    assert edits is not None
    assert len(edits) == 1
    assert edits[0].operation == ApplyOperation.REPLACE_RANGE


def test_applyedit_valid_create_file_parses() -> None:
    edits = _parse_apply_edit_set(
        '[{"path":"new.py","operation":"create_file","content":"# new","reason":"add",'
        '"requirement_refs":["r1"]}]'
    )
    assert edits is not None
    assert edits[0].operation == ApplyOperation.CREATE_FILE


def test_applyedit_valid_delete_file_parses() -> None:
    edits = _parse_apply_edit_set(
        '[{"path":"old.py","operation":"delete_file","reason":"remove","requirement_refs":["r1"]}]'
    )
    assert edits is not None
    assert edits[0].operation == ApplyOperation.DELETE_FILE


def test_applyedit_invalid_json_blocks() -> None:
    result = _parse_apply_edit_set("not json at all")
    assert result is None


def test_applyedit_freeform_text_blocks() -> None:
    result = _parse_apply_edit_set("ok")
    assert result is None


def test_applyedit_json_object_not_array_blocks() -> None:
    result = _parse_apply_edit_set('{"path":"foo.py","operation":"create_file","content":"x"}')
    assert result is None


def test_applyedit_array_with_non_dict_element_blocks() -> None:
    result = _parse_apply_edit_set('["not-an-object"]')
    assert result is None


def test_applyedit_unknown_operation_blocks() -> None:
    result = _parse_apply_edit_set(
        '[{"path":"foo.py","operation":"unknown_op","content":"x","reason":"r","requirement_refs":["r"]}]'
    )
    assert result is None


# ------------------------------------------------------------------ 2.3 Path validation


def test_path_traversal_blocks_via_unsafe_edit_reason() -> None:
    # _unsafe_edit_reason does not check traversal (that is done in apply_edit),
    # but _invalid_edit_contract_reason and _parse_apply_edit_set reject malformed
    # path shapes before reaching apply_edit. Confirm that a traversal path that
    # makes it through parse is caught by apply_edit's root-confinement check.
    from opencontext_core.agents.executor import apply_edit as _apply_edit

    edit = ApplyEdit(
        path="../etc/passwd",
        operation=ApplyOperation.CREATE_FILE,
        content="pwned",
        reason="traversal",
        requirement_refs=["x"],
    )
    with pytest.raises(RuntimeError, match="Path escape"):
        _apply_edit(Path("/tmp"), edit)


def test_absolute_path_blocked_by_apply_edit(tmp_path: Path) -> None:
    edit = ApplyEdit(
        path="/etc/passwd",
        operation=ApplyOperation.CREATE_FILE,
        content="bad",
        reason="absolute",
        requirement_refs=["x"],
    )
    with pytest.raises(RuntimeError, match="Path escape"):
        from opencontext_core.agents.executor import apply_edit as _apply_edit

        _apply_edit(tmp_path, edit)


def test_dotenv_path_is_unsafe_via_unsafe_edit_reason() -> None:
    edit = ApplyEdit(
        path=".env",
        operation=ApplyOperation.CREATE_FILE,
        content="SECRET=x",
        reason="bad",
        requirement_refs=["r"],
    )
    reason = _unsafe_edit_reason(edit)
    assert reason is not None
    assert "forbidden" in reason.lower() or "secret" in reason.lower()


# ------------------------------------------------------------------ 2.4 Range validation


def test_replace_range_missing_start_line_blocks() -> None:
    edit = ApplyEdit(
        path="foo.py",
        operation=ApplyOperation.REPLACE_RANGE,
        end_line=3,
        content="x",
        reason="r",
        requirement_refs=["r"],
    )
    assert _invalid_edit_contract_reason(edit) is not None


def test_replace_range_missing_end_line_blocks() -> None:
    edit = ApplyEdit(
        path="foo.py",
        operation=ApplyOperation.REPLACE_RANGE,
        start_line=1,
        content="x",
        reason="r",
        requirement_refs=["r"],
    )
    assert _invalid_edit_contract_reason(edit) is not None


def test_replace_range_end_before_start_blocks() -> None:
    edits = _parse_apply_edit_set(
        '[{"path":"calc.py","operation":"replace_range","start_line":4,"end_line":2,'
        '"content":"x","reason":"bad","requirement_refs":["c"]}]'
    )
    assert edits is None


def test_replace_range_zero_start_line_blocks() -> None:
    edit = ApplyEdit(
        path="foo.py",
        operation=ApplyOperation.REPLACE_RANGE,
        start_line=0,
        end_line=2,
        content="x",
        reason="r",
        requirement_refs=["r"],
    )
    assert _invalid_edit_contract_reason(edit) is not None


# ------------------------------------------------------------------ 2.7 Valid sampling e2e


def test_mcp_sampling_valid_edit_runs_full_pipeline_and_fixes_bug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 2.7: valid sampling edit flows through pipeline; golden bug is fixed."""
    _pin_mock(monkeypatch)
    work = tmp_path / "fixture"
    shutil.copytree(_GOLDEN, work)
    register_host_sampler(lambda *_: _VALID_EDIT_JSON)

    summary = run_oc_flow_cli("Fix failing test", root=work, workflow="auto", lane="fast")

    assert summary["status"] == "completed"
    fixed = (work / "buggy_add.py").read_text(encoding="utf-8")
    assert "return a + b" in fixed
    receipts_path = Path(summary["artifacts_dir"]) / "apply-receipts.json"
    assert receipts_path.exists()
    payload = json.loads(receipts_path.read_text(encoding="utf-8"))
    # Receipts are stored as {"checkpoint_id": ..., "receipts": [...]}
    receipts = payload.get("receipts", payload) if isinstance(payload, dict) else payload
    assert any(r.get("changed") for r in receipts)


# ------------------------------------------------------------------ 2.8 Malformed response


def test_mcp_sampling_malformed_response_returns_blocked_no_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 2.8: `ok` response is blocked and file is not mutated."""
    _pin_mock(monkeypatch)
    work = tmp_path / "fixture"
    shutil.copytree(_GOLDEN, work)
    original = (work / "buggy_add.py").read_text(encoding="utf-8")
    register_host_sampler(lambda *_: "ok")

    summary = run_oc_flow_cli("Fix failing test", root=work, workflow="auto", lane="fast")

    assert summary["status"] == "blocked"
    assert "sampling response failed ApplyEdit contract validation" in summary["completion_reason"]
    # File must be unchanged
    assert (work / "buggy_add.py").read_text(encoding="utf-8") == original


# ------------------------------------------------------------------ 2.9 Secret .env edit


def test_mcp_sampling_dotenv_edit_blocked_before_apply_env_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 2.9: edit creating .env is blocked before apply; .env must not exist."""
    _pin_mock(monkeypatch)
    work = tmp_path / "fixture"
    shutil.copytree(_GOLDEN, work)
    register_host_sampler(
        lambda *_: (
            '[{"path":".env","operation":"create_file","content":"OPENAI_API_KEY=sk-test",'
            '"reason":"bad","requirement_refs":["c"]}]'
        )
    )

    summary = run_oc_flow_cli("Fix failing test", root=work, workflow="auto", lane="fast")

    assert summary["status"] == "blocked"
    assert not (work / ".env").exists()

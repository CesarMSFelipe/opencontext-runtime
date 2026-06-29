"""Productive NodeExecutor + ApplyEdit contract (B8 / AVH-015).

The provider-backed executor turns OC Flow's mutation seam productive: it asks an
injected provider gateway for a STRUCTURED, schema-validated ``ApplyEdit`` set and
routes each edit through provider -> validate -> policy -> checkpoint -> apply ->
receipt -> inspection. A deterministic provider STUB (honest, no real model) lets
these tests exercise the FULL pipeline. The three R1 scenarios: valid edit fixes the
bug and verifies; malformed edits block (no mutation); a forbidden path is denied.
"""

from __future__ import annotations

import sys
from pathlib import Path

from opencontext_core.models.llm import LLMResponse
from opencontext_core.oc_flow.models import Lane
from opencontext_core.oc_flow.nodes import (
    McpSamplingNodeExecutor,
    ProviderBackedNodeExecutor,
)
from opencontext_core.oc_flow.runner import OCFlowRunner


class _StubGateway:
    """Deterministic provider stub: returns a fixed response, records the calls.

    This is honest — it exercises the real executor pipeline (parse, schema-validate,
    policy, checkpoint, apply, receipt, inspection); it does not fake a pass.
    """

    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[object] = []

    def generate(self, request: object) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(
            content=self._content,
            provider="mock",
            model="stub",
            input_tokens=1,
            output_tokens=1,
        )


def _seed_buggy_calc(root: Path) -> None:
    (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")


# A schema-valid ApplyEdit set that fixes the off-by-operator bug on line 2.
_VALID_EDIT_JSON = (
    '[{"path":"calc.py","operation":"replace_range","start_line":2,"end_line":2,'
    '"content":"    return a + b","reason":"fix the operator",'
    '"requirement_refs":["add returns the sum"]}]'
)


def _verify_cmd() -> list[str]:
    return [
        sys.executable,
        "-c",
        "import sys; sys.path.insert(0, '.'); import calc; assert calc.add(2, 3) == 5",
    ]


# ------------------------------------------------------------------- provider-free path
def test_provider_free_mutation_task_not_completed(tmp_path: Path) -> None:
    # No provider/executor configured (default deterministic) → never `completed`.
    _seed_buggy_calc(tmp_path)
    result = OCFlowRunner(root=tmp_path).run("Fix failing test", lane=Lane.FAST)
    assert result.status != "completed"
    assert result.status in {"needs_executor", "blocked", "escalated", "needs_provider"}
    # No mutation was made; the bug remains.
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a - b\n"


# ----------------------------------------------------- R1 (a): valid ApplyEdit → fixed
def test_provider_valid_apply_edit_fixes_bug_and_verifies(tmp_path: Path) -> None:
    _seed_buggy_calc(tmp_path)
    gateway = _StubGateway(_VALID_EDIT_JSON)
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")
    result = OCFlowRunner(root=tmp_path, executor=executor).run(
        "Fix failing test",
        lane=Lane.FAST,
        run_external_inspection=True,
        test_command=_verify_cmd(),
    )
    assert gateway.calls  # the full pipeline really called the provider
    assert result.status == "completed"
    # The bug is actually fixed and verified.
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a + b\n"
    # A receipt records the applied edit; inspection ran.
    receipts = (result.artifacts_dir / "apply-receipts.json").read_text(encoding="utf-8")
    assert "calc.py" in receipts
    assert (result.artifacts_dir / "inspection-report.json").exists()


def test_mcp_sampling_executor_uses_same_pipeline(tmp_path: Path) -> None:
    _seed_buggy_calc(tmp_path)
    gateway = _StubGateway(_VALID_EDIT_JSON)
    executor = McpSamplingNodeExecutor(gateway=gateway, root=tmp_path)
    result = OCFlowRunner(root=tmp_path, executor=executor).run(
        "Fix failing test",
        lane=Lane.FAST,
        run_external_inspection=True,
        test_command=_verify_cmd(),
    )
    assert result.status == "completed"
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a + b\n"


# ------------------------------------------------ R1 (b): malformed edits → blocked
def test_provider_malformed_edits_block_run_no_mutation(tmp_path: Path) -> None:
    _seed_buggy_calc(tmp_path)
    gateway = _StubGateway("Sure! Here is the fix you asked for, no JSON though.")
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")
    result = OCFlowRunner(root=tmp_path, executor=executor).run(
        "Fix failing test",
        lane=Lane.FAST,
    )
    assert result.status != "completed"
    assert result.status == "blocked"
    assert "unparseable" in result.completion_reason or "schema" in result.completion_reason
    # No file was mutated.
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a - b\n"


def test_provider_schema_invalid_edits_block_run(tmp_path: Path) -> None:
    _seed_buggy_calc(tmp_path)
    # A JSON array but the element is not a valid ApplyEdit (bad operation + extra key).
    bad = '[{"path":"calc.py","operation":"nuke_everything","wat":1}]'
    gateway = _StubGateway(bad)
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")
    result = OCFlowRunner(root=tmp_path, executor=executor).run(
        "Fix failing test",
        lane=Lane.FAST,
    )
    assert result.status == "blocked"
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a - b\n"


# ------------------------------------------- R1 (c): forbidden path → policy denies
def test_provider_forbidden_path_denied_by_policy(tmp_path: Path) -> None:
    _seed_buggy_calc(tmp_path)
    # A schema-valid edit whose target escapes the run root.
    escape = (
        '[{"path":"../escape.py","operation":"create_file","content":"x = 1\\n",'
        '"reason":"escape","requirement_refs":["c"]}]'
    )
    gateway = _StubGateway(escape)
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")
    result = OCFlowRunner(root=tmp_path, executor=executor).run(
        "Fix failing test",
        lane=Lane.FAST,
    )
    assert result.status == "blocked"
    assert "policy denied" in result.completion_reason
    # No file was written anywhere — inside or outside the root.
    assert not (tmp_path.parent / "escape.py").exists()
    assert (tmp_path / "calc.py").read_text() == "def add(a, b):\n    return a - b\n"

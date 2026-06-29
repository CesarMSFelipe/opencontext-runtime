"""Real provider executor wired into the ``run`` CLI (VDM-005 / Phase 5).

``oc_flow/cli.run_oc_flow_cli`` resolves a productive executor from the ambient
environment: a real (non-mock) provider yields a ``ProviderBackedNodeExecutor`` that
mutates through the full provider -> validate -> policy -> checkpoint -> apply ->
receipt -> inspection -> verify pipeline; no provider keeps the executor absent so a
mutation task stays honestly ``needs_executor`` (never a false ``completed``).

We have no live credentials, so the end-to-end "real fix" proof injects a DETERMINISTIC
stub gateway (the documented test hook — an explicit ``executor=`` wins over detection).
This is honest: the stub only stands in for the network round-trip; every other stage
(parse, schema-validate, policy, checkpoint, apply, receipt, inspection) is the real
production code path exercised through the actual CLI entry point.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from opencontext_core.models.llm import LLMResponse
from opencontext_core.oc_flow import cli as oc_flow_cli
from opencontext_core.oc_flow.cli import _resolve_executor, run_oc_flow_cli
from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
from opencontext_core.providers.detect import DetectedProvider

# A schema-valid ApplyEdit set that fixes the off-by-operator bug on line 2 of calc.py.
_VALID_EDIT_JSON = (
    '[{"path":"calc.py","operation":"replace_range","start_line":2,"end_line":2,'
    '"content":"    return a + b","reason":"fix the operator",'
    '"requirement_refs":["add returns the sum"]}]'
)

_BUGGY = "def add(a, b):\n    return a - b\n"
_FIXED = "def add(a, b):\n    return a + b\n"
_SEED_TEST = "from calc import add\n\n\ndef test_add_returns_sum():\n    assert add(2, 3) == 5\n"


class _StubGateway:
    """Deterministic provider stand-in: returns a fixed response, records the calls.

    Honest — it only replaces the network call; the executor still parses, schema-
    validates, policy-checks, checkpoints, applies, receipts and inspects for real.
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
    (root / "calc.py").write_text(_BUGGY, encoding="utf-8")
    (root / "test_calc.py").write_text(_SEED_TEST, encoding="utf-8")


def _run_seeded_test(root: Path) -> subprocess.CompletedProcess[str]:
    # PYTHONDONTWRITEBYTECODE: the pre-fix run and the post-fix run import the SAME
    # ``calc`` module whose source differs only by one operator (identical byte size,
    # possibly same-second mtime); without this a stale ``.pyc`` from the first run
    # would mask the fix. No bytecode is written, so each run recompiles from source.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "test_calc.py",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
    )


# ------------------------------------------------------------- 5.3(b): real provider wires
def test_real_provider_detected_builds_provider_backed_executor(tmp_path, monkeypatch):
    """A non-mock detected provider constructs a productive ProviderBackedNodeExecutor."""
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(
            name="anthropic",
            api_key="sk-test",
            model="claude-sonnet-4-6",
            source="ANTHROPIC_API_KEY",
        ),
    )
    executor = _resolve_executor(tmp_path)
    assert isinstance(executor, ProviderBackedNodeExecutor)
    # The completion gate reads this to mean "a productive executor exists".
    assert getattr(executor, "provider_available", False) is True


def test_no_provider_resolves_to_none(tmp_path, monkeypatch):
    """A mock detection (no creds, no local server) leaves the executor absent."""
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )
    assert _resolve_executor(tmp_path) is None


def test_provider_without_adapter_stays_honest(tmp_path, monkeypatch):
    """A detected provider with no buildable adapter (google/mistral) stays None."""
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(
            name="google",
            api_key="g-test",
            model="gemini-2.0-flash",
            source="GEMINI_API_KEY",
        ),
    )
    assert _resolve_executor(tmp_path) is None


# ------------------------------------------------- 5.3(a): no provider -> honest needs_executor
def test_no_provider_mutation_task_needs_executor(tmp_path, monkeypatch):
    """Through the real CLI path, a mutation task with no provider never completes."""
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )
    _seed_buggy_calc(tmp_path)
    summary = run_oc_flow_cli(
        "Fix failing test",
        root=tmp_path,
        workflow="auto",
        lane="fast",
    )
    assert summary["status"] == "needs_executor"
    assert summary["status"] != "completed"
    # No mutation was made; the bug remains.
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == _BUGGY


# ------------------------------------------------- 5.3(c): read-only task unaffected by provider
def test_read_only_task_completes_without_provider(tmp_path, monkeypatch):
    """A read-only analysis task still completes on the provider-free path (no regression)."""
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )
    _seed_buggy_calc(tmp_path)
    summary = run_oc_flow_cli(
        "Summarize the calc module",
        root=tmp_path,
        workflow="auto",
        lane="fast",
    )
    assert summary["status"] == "completed"
    # Read-only: the source is untouched.
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == _BUGGY


# --------------- end-to-end proof: stub provider drives the REAL CLI pipeline to a real fix
def test_stub_provider_through_cli_fixes_bug_and_test_passes(tmp_path):
    """Injecting a stub gateway proves the whole CLI pipeline produces + verifies a real fix."""
    _seed_buggy_calc(tmp_path)
    # Sanity: the seeded test really fails before the fix.
    assert _run_seeded_test(tmp_path).returncode != 0

    gateway = _StubGateway(_VALID_EDIT_JSON)
    executor = ProviderBackedNodeExecutor(gateway=gateway, root=tmp_path, provider="mock")
    summary = run_oc_flow_cli(
        "Fix failing test",
        root=tmp_path,
        workflow="auto",
        lane="fast",
        executor=executor,  # explicit hook wins over detection (injectable)
    )

    assert gateway.calls  # the real pipeline actually called the provider
    assert summary["status"] == "completed"
    # The bug is really fixed on disk.
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == _FIXED
    # patch.diff is a real, non-empty diff naming the changed file.
    artifacts = Path(summary["artifacts_dir"])
    patch = (artifacts / "patch.diff").read_text(encoding="utf-8")
    assert "calc.py" in patch
    assert "no edits proposed" not in patch
    # An apply receipt records the applied edit.
    assert "calc.py" in (artifacts / "apply-receipts.json").read_text(encoding="utf-8")
    # The seeded failing test now passes through the fix the pipeline produced.
    assert _run_seeded_test(tmp_path).returncode == 0


def test_detected_provider_autowires_full_pipeline(tmp_path, monkeypatch):
    """The LIVE auto-wire path (no executor= injected) fixes the bug end-to-end.

    Only the provider's network round-trip is stubbed: ``detect_provider`` reports a
    real provider and ``build_provider_gateway`` yields a stub base gateway, so
    ``_resolve_executor`` composes the genuine ``ProviderGateway`` facade over a
    ``ProviderBackedNodeExecutor`` exactly as it would with live credentials.
    """
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(
            name="anthropic",
            api_key="sk-test",
            model="claude-sonnet-4-6",
            source="ANTHROPIC_API_KEY",
        ),
    )
    monkeypatch.setattr(
        oc_flow_cli,
        "build_provider_gateway",
        lambda name, model: _StubGateway(_VALID_EDIT_JSON),
    )
    _seed_buggy_calc(tmp_path)
    summary = run_oc_flow_cli(
        "Fix failing test",
        root=tmp_path,
        workflow="auto",
        lane="fast",
    )
    assert summary["status"] == "completed"
    assert (tmp_path / "calc.py").read_text(encoding="utf-8") == _FIXED
    assert _run_seeded_test(tmp_path).returncode == 0

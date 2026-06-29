"""TEST-ONLY ``test_stub`` provider resolution + the no-production-fallthrough invariant.

PROD-002 / design B2: ``_resolve_executor`` builds a ``ProviderBackedNodeExecutor`` over
a :class:`TestStubGateway` IFF the resolved ``opencontext.yaml`` EXPLICITLY declares
``provider: test_stub`` together with a resolvable ``edits_file`` under ``root``. The
load-bearing safety property is the inverse: a production config (no ``test_stub``), a
missing / out-of-root ``edits_file``, or no config at all MUST behave exactly as the
pre-change path (executor ``None`` → ``DeterministicNodeExecutor`` → ``needs_executor``)
and MUST NEVER instantiate ``TestStubGateway``.

``detect_provider`` is pinned to ``mock`` throughout so a stray ambient API key cannot
change the branch under test (the ``test_stub`` gate only runs on the ``mock`` path).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from opencontext_core.oc_flow import cli as oc_flow_cli
from opencontext_core.oc_flow.cli import _resolve_executor, run_oc_flow_cli
from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
from opencontext_core.providers.detect import DetectedProvider
from opencontext_core.providers.test_stub import TestStubGateway

_GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "oc_flow_bugfix_python"

# A schema-valid ApplyEdit set that fixes the off-by-operator bug on line 2 of buggy_add.py.
_VALID_EDIT_JSON = (
    '[{"path":"buggy_add.py","operation":"replace_range","start_line":2,"end_line":2,'
    '"content":"    return a + b","reason":"fix the operator",'
    '"requirement_refs":["add returns the sum"]}]'
)
_BUGGY = "def add(a, b):\n    return a - b\n"
_FIXED = "def add(a, b):\n    return a + b\n"


def _pin_mock(monkeypatch) -> None:
    """Pin detection to ``mock`` so only the ``test_stub`` config gate decides the path."""
    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )


def _write_config(root: Path, body: str) -> None:
    (root / "opencontext.yaml").write_text(body, encoding="utf-8")


# ----------------------------------------------------------- (a) test_stub resolves to executor
def test_test_stub_config_builds_provider_backed_executor(tmp_path, monkeypatch) -> None:
    """An explicit ``test_stub`` config + resolvable ``edits_file`` → productive executor."""
    _pin_mock(monkeypatch)
    (tmp_path / "edits.json").write_text(_VALID_EDIT_JSON, encoding="utf-8")
    _write_config(tmp_path, "provider: test_stub\nedits_file: edits.json\n")

    executor = _resolve_executor(tmp_path)

    assert isinstance(executor, ProviderBackedNodeExecutor)
    assert executor._provider == "test_stub"
    # The completion gate reads this to mean "a productive executor exists".
    assert getattr(executor, "provider_available", False) is True


def test_shipped_golden_fixture_resolves_test_stub(monkeypatch) -> None:
    """The shipped golden fixture's ``opencontext.yaml`` resolves a ``test_stub`` executor.

    Read-only: points ``root`` at the real fixture (does not mutate it).
    """
    _pin_mock(monkeypatch)
    assert (_GOLDEN / "opencontext.yaml").is_file(), "golden fixture must ship opencontext.yaml"

    executor = _resolve_executor(_GOLDEN)

    assert isinstance(executor, ProviderBackedNodeExecutor)
    assert executor._provider == "test_stub"


# --------------------------------------------------- (b) production / partial → no fallthrough
def test_production_config_never_builds_test_stub(tmp_path, monkeypatch) -> None:
    """A production config (no ``test_stub``) is identical to pre-change: ``None``, no gateway."""
    _pin_mock(monkeypatch)

    built: list[Path] = []

    class _SpyGateway(TestStubGateway):
        def __init__(self, edits_file: Path) -> None:  # pragma: no cover - must never run
            built.append(edits_file)
            super().__init__(edits_file)

    monkeypatch.setattr(oc_flow_cli, "TestStubGateway", _SpyGateway)
    # A realistic production config: provider lives nested under models, never top-level.
    _write_config(
        tmp_path,
        "project:\n  name: demo\nmodels:\n  default:\n    provider: anthropic\n    model: x\n",
    )

    assert _resolve_executor(tmp_path) is None
    assert built == [], "TestStubGateway must never be instantiated for a production config"


def test_no_config_at_all_is_none(tmp_path, monkeypatch) -> None:
    """No ``opencontext.yaml`` at all → ``None`` (pre-change path), no gateway built."""
    _pin_mock(monkeypatch)
    assert _resolve_executor(tmp_path) is None


def test_test_stub_without_edits_file_is_none(tmp_path, monkeypatch) -> None:
    """``provider: test_stub`` but NO ``edits_file`` declared → ``None`` (→ needs_executor)."""
    _pin_mock(monkeypatch)
    _write_config(tmp_path, "provider: test_stub\n")
    assert _resolve_executor(tmp_path) is None


def test_test_stub_with_missing_edits_file_is_none(tmp_path, monkeypatch) -> None:
    """``edits_file`` declared but the file does not exist → ``None``."""
    _pin_mock(monkeypatch)
    _write_config(tmp_path, "provider: test_stub\nedits_file: nope.json\n")
    assert _resolve_executor(tmp_path) is None


def test_edits_file_escaping_root_is_rejected(tmp_path, monkeypatch) -> None:
    """An ``edits_file`` that escapes ``root`` (path traversal) is rejected → ``None``."""
    _pin_mock(monkeypatch)
    outside = tmp_path.parent / "outside_edits.json"
    outside.write_text(_VALID_EDIT_JSON, encoding="utf-8")
    root = tmp_path / "proj"
    root.mkdir()
    _write_config(root, "provider: test_stub\nedits_file: ../outside_edits.json\n")
    try:
        assert _resolve_executor(root) is None
    finally:
        outside.unlink(missing_ok=True)


# ------------------------------------------------- end-to-end: real resolution fixes the bug
def test_test_stub_run_fixes_bug_without_injection(tmp_path, monkeypatch) -> None:
    """A copied fixture with ``test_stub`` config drives the REAL pipeline to a real fix.

    No executor is injected: ``run_oc_flow_cli`` resolves the ``test_stub`` executor from
    the copied ``opencontext.yaml`` exactly as the live CLI does.
    """
    _pin_mock(monkeypatch)
    work = tmp_path / "fixture"
    shutil.copytree(_GOLDEN, work)
    assert (work / "buggy_add.py").read_text(encoding="utf-8") == _BUGGY

    summary = run_oc_flow_cli("Fix failing test", root=work, workflow="auto", lane="fast")

    assert summary["status"] == "completed"
    assert summary["workflow"] == "oc-flow"
    assert (work / "buggy_add.py").read_text(encoding="utf-8") == _FIXED

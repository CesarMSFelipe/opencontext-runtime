"""PROFILES-RUNTIME: plan §6 profile semantics enforced beyond inert config values.

The doc's ``default`` profile (executor ``test_stub`` + strict TDD) exists as a
built-in overlay, the canonical ``executors:`` config section exists with the
documented defaults, and the runtime executor selection honors an explicit
``executors: {default: test_stub}`` declaration. Runtime enforcement of
``ci``/``local`` interface semantics is pinned in
``tests/cli/test_interface_runtime_gating.py``.
"""

from __future__ import annotations

from pathlib import Path

from opencontext_core.config import OpenContextConfig, default_config_data
from opencontext_core.config_resolver import resolve


def _write(root: Path, body: str) -> None:
    (root / "opencontext.yaml").write_text(body, encoding="utf-8")


def test_executors_section_has_doc_defaults() -> None:
    """PROFILES-RUNTIME: the executors config section exists with doc defaults
    (test_stub, allow_shell=false)."""
    config = OpenContextConfig.model_validate(default_config_data())
    assert config.executors.default == "test_stub"
    assert config.executors.allow_shell is False


def test_default_profile_selects_test_stub_and_strict_tdd(tmp_path: Path) -> None:
    """PROFILES-RUNTIME: the built-in 'default' profile applies executor test_stub + tdd strict."""
    _write(tmp_path, "version: 2\nprofile: default\nproject:\n  name: demo\n")
    resolved = resolve(tmp_path, env={}, global_config={})
    assert resolved.profile == "default"
    assert resolved.config.executors.default == "test_stub"
    assert resolved.config.harness.tdd_mode == "strict"
    assert resolved.provenance.dotted_layer_of("executors.default") == "profile"
    assert resolved.provenance.dotted_layer_of("harness.tdd_mode") == "profile"


def test_implicit_profile_remains_balanced(tmp_path: Path) -> None:
    """PROFILES-RUNTIME: with no profile selected, the implicit profile stays
    'balanced' (recorded deviation from the doc's implicit default)."""
    _write(tmp_path, "version: 2\nproject:\n  name: demo\n")
    resolved = resolve(tmp_path, env={}, global_config={})
    assert resolved.profile == "balanced"
    assert resolved.config.harness.tdd_mode == "ask"


def test_runtime_honors_explicit_executors_default(tmp_path: Path, monkeypatch) -> None:
    """PROFILES-RUNTIME: executor selection honors an explicit
    `executors: {default: test_stub}` section."""
    from opencontext_core.oc_flow import cli as oc_flow_cli
    from opencontext_core.oc_flow.cli import _resolve_executor
    from opencontext_core.oc_flow.nodes import ProviderBackedNodeExecutor
    from opencontext_core.providers.detect import DetectedProvider

    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )
    (tmp_path / "edits.json").write_text(
        '[{"path":"a.py","operation":"replace_range","start_line":1,"end_line":1,'
        '"content":"x = 1","reason":"r","requirement_refs":["req"]}]',
        encoding="utf-8",
    )
    _write(tmp_path, "executors:\n  default: test_stub\nedits_file: edits.json\n")

    executor = _resolve_executor(tmp_path)

    assert isinstance(executor, ProviderBackedNodeExecutor)
    assert executor._provider == "test_stub"


def test_runtime_ignores_typed_default_without_explicit_section(
    tmp_path: Path, monkeypatch
) -> None:
    """PROFILES-RUNTIME: without an explicit executors section, the typed
    default is NOT an opt-in (B2 no-fallthrough preserved)."""
    from opencontext_core.oc_flow import cli as oc_flow_cli
    from opencontext_core.oc_flow.cli import _resolve_executor
    from opencontext_core.providers.detect import DetectedProvider

    monkeypatch.setattr(
        oc_flow_cli,
        "detect_provider",
        lambda: DetectedProvider(name="mock", api_key="", model="mock", source="fallback"),
    )
    (tmp_path / "edits.json").write_text("[]", encoding="utf-8")
    _write(tmp_path, "project:\n  name: demo\nedits_file: edits.json\n")

    assert _resolve_executor(tmp_path) is None

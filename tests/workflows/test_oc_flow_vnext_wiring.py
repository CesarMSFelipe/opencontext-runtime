"""VDM-004 seam wiring (subset A): context_engine + kg_v2 reach the live loop.

Bar: with a flag ON the vNext gather path activates; with both OFF the legacy
executor path is byte-identical. These tests pin BOTH halves — the runner threading
the flags into ``OCFlowContext`` (from explicit ctor args or the project config) and
``node_gather_context`` selecting the right branch off those flags.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import opencontext_core.oc_flow.nodes as nodes_mod
import opencontext_core.oc_flow.runner as runner_mod
from opencontext_core.oc_flow.models import (
    ContextEnvelope,
    ContextEnvelopeItem,
    Lane,
)
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_gather_context,
)
from opencontext_core.oc_flow.runner import OCFlowRunner


def _spy_context(monkeypatch: Any) -> dict[str, Any]:
    """Capture the kwargs the runner passes to OCFlowContext (returns the real one)."""
    captured: dict[str, Any] = {}
    real = runner_mod.OCFlowContext

    def _factory(**kwargs: Any) -> OCFlowContext:
        captured.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(runner_mod, "OCFlowContext", _factory)
    return captured


def _boom(*_a: Any, **_k: Any) -> Any:
    raise AssertionError("gated vNext path ran while its flag was off")


# --------------------------------------------------------------- runner flag plumbing
def test_runner_propagates_explicit_flags_into_context(tmp_path: Path, monkeypatch: Any) -> None:
    captured = _spy_context(monkeypatch)
    runner = OCFlowRunner(root=tmp_path, context_engine_enabled=True, kg_v2_enabled=True)
    runner.run("Fix failing test", lane=Lane.FAST)
    assert captured["context_engine_enabled"] is True
    assert captured["kg_v2_enabled"] is True


def test_runner_reads_flags_from_config(tmp_path: Path, monkeypatch: Any) -> None:
    (tmp_path / "opencontext.yaml").write_text(
        "project:\n  name: x\nruntime:\n  context_engine_enabled: true\n  kg_v2_enabled: true\n",
        encoding="utf-8",
    )
    runner = OCFlowRunner(root=tmp_path)
    assert runner._context_engine_enabled is True
    assert runner._kg_v2_enabled is True
    # ...and the config-resolved flags reach the constructed context.
    captured = _spy_context(monkeypatch)
    runner.run("Fix failing test", lane=Lane.FAST)
    assert captured["context_engine_enabled"] is True
    assert captured["kg_v2_enabled"] is True


def test_runner_flags_default_legacy_off(tmp_path: Path, monkeypatch: Any) -> None:
    # Ledger-driven: with no config file / explicit flags the runner adopts the LIVE
    # config defaults and propagates them faithfully into the context. A subsystem WITHOUT
    # an accepted flip bundle MUST default legacy-off (regression guard); a flipped one
    # (accepted bundle) legitimately defaults vNext-on.
    from opencontext_core.compat.flip_evidence import read_flip_bundles
    from opencontext_core.config import RuntimeMigrationConfig

    repo = Path(__file__).resolve().parents[2]
    accepted = {b.subsystem for b in read_flip_bundles(repo) if b.accepted}
    fields = RuntimeMigrationConfig.model_fields
    exp_ce = bool(fields["context_engine_enabled"].default)
    exp_kg = bool(fields["kg_v2_enabled"].default)
    if "context_engine" not in accepted:
        assert exp_ce is False
    if "knowledge_graph" not in accepted:
        assert exp_kg is False

    captured = _spy_context(monkeypatch)
    runner = OCFlowRunner(root=tmp_path)  # no config file, no explicit flags
    assert runner._context_engine_enabled is exp_ce
    assert runner._kg_v2_enabled is exp_kg
    runner.run("Fix failing test", lane=Lane.FAST)
    assert captured["context_engine_enabled"] is exp_ce
    assert captured["kg_v2_enabled"] is exp_kg
    assert captured["graph_db_path"] is None  # no KG index under tmp_path


def test_runner_explicit_false_overrides_config(tmp_path: Path) -> None:
    # Config says ON; an explicit ctor False must win (cli/test override path).
    (tmp_path / "opencontext.yaml").write_text(
        "project:\n  name: x\nruntime:\n  context_engine_enabled: true\n  kg_v2_enabled: true\n",
        encoding="utf-8",
    )
    runner = OCFlowRunner(root=tmp_path, context_engine_enabled=False, kg_v2_enabled=False)
    assert runner._context_engine_enabled is False
    assert runner._kg_v2_enabled is False


# --------------------------------------------------------------- node-level activation
def _ctx(root: Path, **flags: Any) -> OCFlowContext:
    artifacts = root / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    return OCFlowContext(
        root=root,
        artifacts_dir=artifacts,
        task="Fix failing test",
        lane=Lane.FAST,
        profile="balanced",
        executor=DeterministicNodeExecutor(),
        max_attempts=2,
        seed_paths=[],
        **flags,
    )


def test_gather_context_uses_context_engine_when_enabled(tmp_path: Path, monkeypatch: Any) -> None:
    marker = ContextEnvelope(
        task="Fix failing test",
        items=[ContextEnvelopeItem(source="engine", ref="ce", summary="ce", tokens=10)],
    )
    calls: list[int] = []

    def _fake_engine(ctx: OCFlowContext, depth: int) -> ContextEnvelope:
        calls.append(depth)
        return marker

    monkeypatch.setattr(nodes_mod, "_context_engine_envelope", _fake_engine)
    ctx = _ctx(tmp_path, context_engine_enabled=True)
    node_gather_context(ctx)
    assert calls, "ContextEngine v2 path did not run with the flag on"
    assert ctx.envelope is not None
    assert [i.source for i in ctx.envelope.items] == ["engine"]


def test_gather_context_uses_kg_subgraph_when_enabled(tmp_path: Path, monkeypatch: Any) -> None:
    kg_items = [ContextEnvelopeItem(source="kg", ref="m.py", summary="fn", tokens=80)]
    monkeypatch.setattr(nodes_mod, "_kg_v2_seed_items", lambda ctx: kg_items)
    # KG items win: the ContextEngine path must NOT be reached even when also enabled.
    monkeypatch.setattr(nodes_mod, "_context_engine_envelope", _boom)
    ctx = _ctx(
        tmp_path,
        kg_v2_enabled=True,
        context_engine_enabled=True,
        graph_db_path=tmp_path / "graph.db",
    )
    result = node_gather_context(ctx)
    assert result.outputs["kg_consulted"] is True
    assert ctx.envelope is not None
    assert all(i.source == "kg" for i in ctx.envelope.items)


def test_gather_context_legacy_when_both_off(tmp_path: Path, monkeypatch: Any) -> None:
    # With both flags off the gated branches must not even be consulted.
    monkeypatch.setattr(nodes_mod, "_kg_v2_seed_items", _boom)
    monkeypatch.setattr(nodes_mod, "_context_engine_envelope", _boom)
    ctx = _ctx(tmp_path)  # both flags default off
    result = node_gather_context(ctx)
    assert result.outputs["kg_consulted"] is False
    assert ctx.envelope is not None  # legacy executor produced the envelope

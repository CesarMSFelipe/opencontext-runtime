"""TDD — P0.5: KG grounding + P1.2: context-receipt.json.

P0.5 RED: node_gather_context falls back to memory:task-statement-fallback instead of
seeding from the KG when seeds are empty, because (a) ContextEnvelopeItem has no
confidence field and (b) the opportunistic KG path does not exist.

P1.2 RED: context-receipt.json is not written next to context-envelope.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import opencontext_core.oc_flow.nodes as nodes_mod
from opencontext_core.oc_flow.models import (
    ContextEnvelopeItem,
    Lane,
)
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_gather_context,
)


def _ctx(root: Path, **flags: Any) -> OCFlowContext:
    artifacts = root / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {
        "root": root,
        "artifacts_dir": artifacts,
        "task": "Fix session store resume bug",
        "lane": Lane.FAST,
        "profile": "balanced",
        "executor": DeterministicNodeExecutor(),
        "max_attempts": 2,
        "seed_paths": [],
    }
    kwargs.update(flags)
    return OCFlowContext(**kwargs)


# ------------------------------------------------------------------ P0.5 model contract
def test_context_envelope_item_has_confidence_field() -> None:
    """ContextEnvelopeItem must expose a per-item confidence field (default 0.0)."""
    item = ContextEnvelopeItem(source="kg", ref="src/session_store.py")
    assert hasattr(item, "confidence"), "ContextEnvelopeItem must have a confidence field"
    assert isinstance(item.confidence, float)
    assert item.confidence >= 0.0


def test_context_envelope_item_accepts_confidence_on_construction() -> None:
    """ContextEnvelopeItem must accept an explicit confidence value on construction."""
    item = ContextEnvelopeItem(
        source="kg",
        ref="src/session_store.py",
        summary="module session_store",
        tokens=80,
        why_included="kg:score=1.00",
        confidence=1.0,
    )
    assert item.confidence == 1.0


# ------------------------------------------------------------------ P0.5 grounding path
def test_gather_context_grounds_on_kg_when_db_available(tmp_path: Path, monkeypatch: Any) -> None:
    """When graph_db_path is set and seed_paths is empty, node_gather_context must
    query the KG and produce ≥1 envelope item with ref ending in session_store.py and
    confidence > 0 (not the memory:task-statement-fallback placeholder).

    This is the P0.5 RED gate: without the opportunistic KG path the envelope would
    only contain the fallback memory item (confidence=0.0).
    """
    kg_item = ContextEnvelopeItem(
        source="kg",
        ref="src/session_store.py",
        summary="module session_store",
        tokens=80,
        why_included="kg:score=1.00",
        confidence=1.0,
    )
    monkeypatch.setattr(nodes_mod, "_kg_v2_seed_items", lambda _ctx: [kg_item])

    # Provide a non-None graph_db_path to activate the opportunistic path;
    # the file need not exist because _kg_v2_seed_items is monkeypatched.
    ctx = _ctx(tmp_path, graph_db_path=tmp_path / "context_graph.db")
    node_gather_context(ctx)

    assert ctx.envelope is not None
    kg_items_in_envelope = [
        i for i in ctx.envelope.items if i.ref.endswith("session_store.py") and i.confidence > 0
    ]
    _items_debug = [
        {"ref": i.ref, "why_included": i.why_included, "confidence": i.confidence}
        for i in ctx.envelope.items
    ]
    assert kg_items_in_envelope, (
        "Expected ≥1 envelope item with ref ending in session_store.py and confidence > 0; "
        f"got items={_items_debug}"
    )


def test_gather_context_does_not_ground_on_kg_without_db(tmp_path: Path, monkeypatch: Any) -> None:
    """Without graph_db_path the opportunistic KG path must be skipped entirely.
    Legacy behaviour: executor produces the memory fallback, kg_consulted = False."""
    calls: list[int] = []

    def _spy(ctx: Any) -> Any:
        calls.append(1)
        return None  # simulate empty KG

    monkeypatch.setattr(nodes_mod, "_kg_v2_seed_items", _spy)

    ctx = _ctx(tmp_path)  # graph_db_path defaults to None
    result = node_gather_context(ctx)

    assert calls == [], "_kg_v2_seed_items must NOT be called when graph_db_path is None"
    assert result.outputs["kg_consulted"] is False


def test_gather_context_fallback_item_has_confidence_zero(tmp_path: Path) -> None:
    """The memory:task-statement-fallback item must carry confidence=0.0 (default),
    distinguishable from KG items which should carry confidence>0."""
    ctx = _ctx(tmp_path)  # no KG, no seeds → memory fallback
    node_gather_context(ctx)

    assert ctx.envelope is not None
    fallback_items = [
        i
        for i in ctx.envelope.items
        if i.source == "memory" and "task-statement-fallback" in i.why_included
    ]
    assert fallback_items, "Expected at least one memory:task-statement-fallback item"
    for item in fallback_items:
        assert item.confidence == 0.0, (
            f"Fallback item must have confidence=0.0, got {item.confidence}"
        )


# ------------------------------------------------------------------ P0.5 runner wiring
def test_runner_always_resolves_graph_db_path_when_indexed(tmp_path: Path) -> None:
    """OCFlowRunner must resolve graph_db_path from the storage directory even when
    kg_v2_enabled is False (enabling opportunistic KG seeding by default)."""
    from opencontext_core.oc_flow.runner import OCFlowRunner
    from opencontext_core.paths import StorageMode, resolve_storage_path

    # Create the storage dir + a fake context_graph.db so it looks indexed.
    storage = resolve_storage_path(tmp_path, StorageMode.local)
    storage.mkdir(parents=True, exist_ok=True)
    (storage / "context_graph.db").write_bytes(b"")

    runner = OCFlowRunner(root=tmp_path, kg_v2_enabled=False)
    assert runner._graph_db_path is not None, (
        "graph_db_path must be resolved even when kg_v2_enabled=False "
        "so the opportunistic KG seeding path can activate"
    )
    assert runner._graph_db_path.name == "context_graph.db"


# ------------------------------------------------------------------ P1.2: receipt artifact
def test_gather_context_writes_context_receipt_json(tmp_path: Path) -> None:
    """node_gather_context must persist context-receipt.json in the artifacts dir."""
    ctx = _ctx(tmp_path)
    node_gather_context(ctx)

    receipt_path = ctx.artifacts_dir / "context-receipt.json"
    assert receipt_path.exists(), "context-receipt.json must be written by node_gather_context"


def test_context_receipt_receipt_id_matches_envelope(tmp_path: Path) -> None:
    """context-receipt.json receipt_id must match context-envelope.json receipt_id."""
    ctx = _ctx(tmp_path)
    node_gather_context(ctx)

    env_path = ctx.artifacts_dir / "context-envelope.json"
    receipt_path = ctx.artifacts_dir / "context-receipt.json"
    assert env_path.exists() and receipt_path.exists()

    envelope_data = json.loads(env_path.read_text(encoding="utf-8"))
    receipt_data = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert "receipt_id" in receipt_data, "context-receipt.json must contain receipt_id"
    assert receipt_data["receipt_id"] == envelope_data["receipt_id"], (
        f"receipt receipt_id {receipt_data['receipt_id']!r} must match "
        f"envelope receipt_id {envelope_data['receipt_id']!r}"
    )


def test_context_receipt_schema_fields_present(tmp_path: Path) -> None:
    """context-receipt.json must include: receipt_id, items, omissions, budget,
    ranking_hash, decision_dependency, confidence."""
    ctx = _ctx(tmp_path)
    node_gather_context(ctx)

    receipt_path = ctx.artifacts_dir / "context-receipt.json"
    data = json.loads(receipt_path.read_text(encoding="utf-8"))

    required_keys = {
        "receipt_id",
        "items",
        "omissions",
        "budget",
        "ranking_hash",
        "confidence",
        "decision_dependency",
    }
    missing = required_keys - set(data.keys())
    assert not missing, f"context-receipt.json is missing keys: {missing}, got: {list(data)}"
    assert isinstance(data["items"], list)
    assert isinstance(data["omissions"], list)
    assert isinstance(data["budget"], dict)
    assert "used" in data["budget"] and "available" in data["budget"]


def test_context_receipt_items_have_why_included(tmp_path: Path) -> None:
    """Each item in context-receipt.json must carry a why_included key."""
    ctx = _ctx(tmp_path, seed_paths=["some_file.py"])
    node_gather_context(ctx)

    receipt_path = ctx.artifacts_dir / "context-receipt.json"
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    for item in items:
        assert "why_included" in item, f"receipt item missing why_included: {item}"

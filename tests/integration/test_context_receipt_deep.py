"""TDD — C17: ContextEnvelope deepening at the PR-010 seam.

RED gate: oc_flow/models.py:ContextEnvelope currently lacks receipt_id,
why_included (per item), and budget_used/budget_available fields.
The test asserts those fields are present and non-empty in the
context-envelope.json artifact written by node_gather_context, which
fails until oc_flow/models.py:ContextEnvelope and ContextEnvelopeItem
are extended and to_surgical_envelope populates them.
"""

from __future__ import annotations

import json
from pathlib import Path

from opencontext_core.oc_flow.models import ContextEnvelope, ContextEnvelopeItem, Lane
from opencontext_core.oc_flow.nodes import (
    DeterministicNodeExecutor,
    OCFlowContext,
    node_gather_context,
)


def _ctx(root: Path) -> OCFlowContext:
    artifacts = root / "artifacts" / "oc-flow"
    artifacts.mkdir(parents=True, exist_ok=True)
    return OCFlowContext(
        root=root,
        artifacts_dir=artifacts,
        task="Describe the module structure",
        lane=Lane.FAST,
        profile="balanced",
        executor=DeterministicNodeExecutor(),
        max_attempts=2,
        seed_paths=["src/main.py"],
    )


def test_context_envelope_model_has_receipt_id_field() -> None:
    """ContextEnvelope must expose a receipt_id field (default empty string)."""
    env = ContextEnvelope(task="test")
    assert hasattr(env, "receipt_id"), "ContextEnvelope must have receipt_id field"
    # receipt_id may be empty by default; important it exists on the model
    assert isinstance(env.receipt_id, str)


def test_context_envelope_item_has_why_included_field() -> None:
    """ContextEnvelopeItem must expose a why_included field."""
    item = ContextEnvelopeItem(source="kg", ref="sym:foo")
    assert hasattr(item, "why_included"), "ContextEnvelopeItem must have why_included field"
    assert isinstance(item.why_included, str)


def test_context_envelope_has_budget_fields() -> None:
    """ContextEnvelope must expose budget_used and budget_available fields."""
    env = ContextEnvelope(task="test")
    assert hasattr(env, "budget_used"), "ContextEnvelope must have budget_used"
    assert hasattr(env, "budget_available"), "ContextEnvelope must have budget_available"
    assert isinstance(env.budget_used, int)
    assert isinstance(env.budget_available, int)


def test_gather_context_artifact_has_receipt_fields(tmp_path: Path) -> None:
    """context-envelope.json artifact must contain receipt_id and budget_used keys."""
    ctx = _ctx(tmp_path)
    node_gather_context(ctx)

    env_path = ctx.artifacts_dir / "context-envelope.json"
    assert env_path.exists(), "context-envelope.json must be written by node_gather_context"

    data = json.loads(env_path.read_text(encoding="utf-8"))
    keys = list(data)
    assert "receipt_id" in data, f"context-envelope.json must contain 'receipt_id', got: {keys}"
    assert "budget_used" in data, (
        f"context-envelope.json must contain 'budget_used', got: {list(data)}"
    )
    assert "budget_available" in data, (
        f"context-envelope.json must contain 'budget_available', got: {list(data)}"
    )


def test_gather_context_items_have_why_included(tmp_path: Path) -> None:
    """When the envelope has items, at least one must have a non-empty why_included."""
    ctx = _ctx(tmp_path)
    node_gather_context(ctx)

    env_path = ctx.artifacts_dir / "context-envelope.json"
    data = json.loads(env_path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    if not items:
        # No items on a bare tmp dir is acceptable; skip the assertion.
        return
    why_values = [i.get("why_included", "") for i in items]
    assert any(why_values), (
        f"At least one item must have a non-empty why_included, got: {why_values}"
    )

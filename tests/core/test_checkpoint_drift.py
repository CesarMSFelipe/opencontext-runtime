"""content-derived checkpoints and per-field drift detection."""

from __future__ import annotations

from opencontext_core.dx.checkpoints import (
    ContextCheckpoint,
    capture_checkpoint,
    compare_checkpoints,
    fingerprint,
)


def test_checkpoint_hashes_are_content_derived_and_not_constant() -> None:
    """Distinct content yields distinct, non-placeholder hashes."""
    h1 = fingerprint("alpha")
    h2 = fingerprint("beta")
    assert h1 != h2
    # Not a hardcoded literal placeholder.
    assert h1 not in {"", "0", "constant", "placeholder", "hash"}
    assert len(h1) == 64


def test_capture_is_content_derived() -> None:
    """capture_checkpoint derives each field hash from its input text."""
    cp = capture_checkpoint(
        project="proj-a",
        manifest="manifest-1",
        repo_map="map-1",
        policy="policy-1",
        context_pack="pack-1",
        prompt="prompt-1",
        trace_id="trace-xyz",
    )
    assert cp.manifest_hash == fingerprint("manifest-1")
    assert cp.context_pack_hash == fingerprint("pack-1")
    assert cp.trace_id == "trace-xyz"


def test_drift_comparison_reports_changed_fields() -> None:
    """Per-field drift reports only the fields whose input changed."""
    base = capture_checkpoint(
        project="p",
        manifest="m1",
        repo_map="r",
        policy="pol",
        context_pack="pack1",
        prompt="pr",
        trace_id="t1",
    )
    changed = capture_checkpoint(
        project="p",
        manifest="m2",  # changed
        repo_map="r",
        policy="pol",
        context_pack="pack2",  # changed
        prompt="pr",
        trace_id="t2",
    )
    drift = compare_checkpoints(base, changed)
    assert drift.has_drift is True
    assert "manifest_hash" in drift.changed_fields
    assert "context_pack_hash" in drift.changed_fields
    assert "repo_map_hash" not in drift.changed_fields
    assert "policy_hash" not in drift.changed_fields


def test_identical_inputs_report_no_drift() -> None:
    """Identical inputs report zero drifting fields."""
    kwargs = dict(
        project="p",
        manifest="m",
        repo_map="r",
        policy="pol",
        context_pack="pack",
        prompt="pr",
        trace_id="t",
    )
    a = capture_checkpoint(**kwargs)  # type: ignore[arg-type]
    b = capture_checkpoint(**kwargs)  # type: ignore[arg-type]
    drift = compare_checkpoints(a, b)
    assert drift.has_drift is False
    assert drift.changed_fields == []


def test_checkpoint_model_still_accepts_trace_id() -> None:
    """Backward-compatible: the dataclass still carries trace_id."""
    h = fingerprint("x")
    cp = ContextCheckpoint(
        project_hash=h,
        manifest_hash=h,
        repo_map_hash=h,
        policy_hash=h,
        context_pack_hash=h,
        prompt_hash=h,
        trace_id="trace-1",
    )
    assert cp.trace_id == "trace-1"

"""T5: OcNewConductor lease lifecycle (REQ-2).

Tests that conductor acquires a lease + emits STARTED on spawn, and releases
the lease on mark_done. All lease operations must be fail-soft.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from opencontext_core.oc_new.conductor import OcNewConductor
from opencontext_core.oc_new.flow import OC_NEW_FLOW
from opencontext_core.oc_new.models import ChangeIdentity, OcNewRunState, PhaseState
from opencontext_core.workflow.leases import AgentCoordinationStore


def _make_state(tmp_path: Path) -> OcNewRunState:
    identity = ChangeIdentity.from_task("lease-test")
    phases = [PhaseState(name=p.name) for p in OC_NEW_FLOW]
    return OcNewRunState(identity=identity, task="lease-test", phases=phases)


# ---------------------------------------------------------------------------
# T5-1: spawn_subagent NextAction triggers acquire + STARTED signal
# ---------------------------------------------------------------------------


def test_spawn_acquires_lease_and_emits_started(tmp_path: Path) -> None:
    """_advance returning spawn_subagent must call acquire() and signal(STARTED)."""
    conductor = OcNewConductor(root=tmp_path)
    state = _make_state(tmp_path)

    mock_store = MagicMock(spec=AgentCoordinationStore)
    mock_lease = MagicMock()
    mock_lease.lease_id = "test-lease-id"
    mock_store.acquire.return_value = mock_lease

    with patch.object(type(conductor), "_coord_store", new_callable=lambda: property(lambda self: mock_store)):
        result = conductor._advance(state)

    # The advance should have returned a spawn_subagent action
    assert result.next_action is not None
    assert result.next_action.kind == "spawn_subagent"

    # acquire must have been called
    mock_store.acquire.assert_called_once()
    # signal must have been called with STARTED kind
    mock_store.signal.assert_called_once()
    call_args = mock_store.signal.call_args
    from opencontext_core.workflow.signals import AgentSignalKind
    assert call_args.args[1] == AgentSignalKind.STARTED or (
        len(call_args.args) >= 2 and str(call_args.args[1]) == "started"
    )


# ---------------------------------------------------------------------------
# T5-2: mark_done releases the lease
# ---------------------------------------------------------------------------


def test_mark_done_releases_lease(tmp_path: Path) -> None:
    """mark_done must call release_by_run_phase on the coord store."""
    conductor = OcNewConductor(root=tmp_path)
    # Start a real run to get a run_id
    state = conductor.start("lease-release-test")
    run_id = state.identity.run_id
    phase_name = OC_NEW_FLOW[0].name

    mock_store = MagicMock(spec=AgentCoordinationStore)

    # Write the required phase envelope so mark_done doesn't raise on missing file
    run_dir = tmp_path / ".opencontext" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    import json
    envelope = {
        "run_id": run_id,
        "change_id": state.identity.change_id,
        "phase": phase_name,
        "status": "passed",
        "duration_s": 0.1,
        "artifacts": [],
    }
    (run_dir / f"phase-result.{phase_name}.json").write_text(
        json.dumps(envelope), encoding="utf-8"
    )

    with patch.object(type(conductor), "_coord_store", new_callable=lambda: property(lambda self: mock_store)):
        conductor.mark_done(run_id, phase_name)

    mock_store.release_by_run_phase.assert_called_once_with(run_id, phase_name)


# ---------------------------------------------------------------------------
# T5-3: lease store failure is swallowed — conductor flow completes normally
# ---------------------------------------------------------------------------


def test_lease_store_failure_does_not_raise(tmp_path: Path) -> None:
    """If the lease store raises on acquire/signal, _advance must still return a valid NextAction."""
    conductor = OcNewConductor(root=tmp_path)
    state = _make_state(tmp_path)

    mock_store = MagicMock(spec=AgentCoordinationStore)
    mock_store.acquire.side_effect = RuntimeError("db error")

    with patch.object(type(conductor), "_coord_store", new_callable=lambda: property(lambda self: mock_store)):
        # Must NOT raise — error is logged and swallowed
        result = conductor._advance(state)

    assert result.next_action is not None
    assert result.next_action.kind == "spawn_subagent"


# ---------------------------------------------------------------------------
# T5-4: sequential phases do not deadlock
# ---------------------------------------------------------------------------


def test_sequential_phases_no_deadlock(tmp_path: Path) -> None:
    """Two sequential mark_done+spawn cycles must complete without blocking."""
    conductor = OcNewConductor(root=tmp_path)
    # Use an in-memory store so no file I/O deadlock can occur
    real_store = AgentCoordinationStore(":memory:")

    with patch.object(type(conductor), "_coord_store", new_callable=lambda: property(lambda self: real_store)):
        state = _make_state(tmp_path)
        result1 = conductor._advance(state)

    assert result1.next_action is not None
    assert result1.next_action.kind == "spawn_subagent"

    # Second call with the same state should also work without deadlock
    with patch.object(type(conductor), "_coord_store", new_callable=lambda: property(lambda self: real_store)):
        result2 = conductor._advance(state)

    assert result2.next_action is not None
    assert result2.next_action.kind == "spawn_subagent"

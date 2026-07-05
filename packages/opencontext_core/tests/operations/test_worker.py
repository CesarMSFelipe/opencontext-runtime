"""Tests for ``opencontext_core.operations.worker``.

Covers REQ-ops-deploy-002 from the spec:
- ``RemoteWorkerConnection`` is the contract used for REMOTE / HYBRID modes
- ``connect``, ``submit_job``, ``disconnect`` lifecycle
- ``submit_job`` returns a ``JobHandle`` with a status
- The local in-process worker handles LOCAL / CI_RUNNER / AIR_GAPPED modes
"""

from __future__ import annotations

from typing import Any

import pytest

from opencontext_core.operations.deploy import DeployMode
from opencontext_core.operations.worker import (
    InProcessWorker,
    JobHandle,
    RemoteWorkerConnection,
    build_worker_for_mode,
)


class _FakeRemote(RemoteWorkerConnection):
    """Test double — never touches the network."""

    def __init__(self) -> None:
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.submitted: list[dict[str, Any]] = []
        self._connected = False

    def connect(self) -> None:
        self.connect_calls += 1
        self._connected = True

    def disconnect(self) -> None:
        self.disconnect_calls += 1
        self._connected = False

    def submit_job(self, payload: dict[str, Any]) -> JobHandle:
        assert self._connected, "submit_job before connect"
        self.submitted.append(payload)
        return JobHandle(id="job-1", status="queued", mode=DeployMode.SHARED_REMOTE)


class TestRemoteWorkerConnectionContract:
    def test_lifecycle_connect_then_submit_then_disconnect(self):
        # GIVEN a fresh fake remote worker
        w = _FakeRemote()
        # WHEN the full lifecycle runs
        w.connect()
        handle = w.submit_job({"workflow": "oc-flow", "task": "Fix failing test"})
        w.disconnect()
        # THEN submit was called once, disconnect once, handle reports queued
        assert w.connect_calls == 1
        assert w.disconnect_calls == 1
        assert len(w.submitted) == 1
        assert handle.status == "queued"
        assert handle.id == "job-1"

    def test_submit_job_payload_preserved(self):
        # GIVEN a worker with a specific payload
        w = _FakeRemote()
        w.connect()
        payload = {"workflow": "oc-flow", "task": "Refactor auth", "priority": "high"}
        # WHEN submit_job runs
        w.submit_job(payload)
        # THEN the payload is forwarded unchanged
        assert w.submitted == [payload]

    def test_disconnect_is_idempotent(self):
        # GIVEN a worker that has been disconnected once
        w = _FakeRemote()
        w.connect()
        w.disconnect()
        # WHEN disconnect runs again
        # THEN it does not raise (safe to call repeatedly)
        w.disconnect()
        assert w.disconnect_calls == 2


class TestJobHandle:
    def test_carries_id_status_and_mode(self):
        # GIVEN a handle from a remote worker
        h = JobHandle(id="abc", status="queued", mode=DeployMode.SHARED_REMOTE)
        # THEN the 3 fields are readable
        assert h.id == "abc"
        assert h.status == "queued"
        assert h.mode is DeployMode.SHARED_REMOTE


class TestInProcessWorker:
    def test_runs_jobs_locally(self):
        # GIVEN an in-process worker
        w = InProcessWorker()
        # WHEN a job is submitted
        handle = w.submit_job({"workflow": "oc-flow", "task": "noop"})
        # THEN it returns a completed handle (no queue, no remote)
        assert handle.status == "completed"
        assert handle.mode in {
            DeployMode.LOCAL,
            DeployMode.CI_RUNNER,
            DeployMode.AIR_GAPPED,
        }

    def test_is_also_a_remote_worker_connection(self):
        # InProcessWorker must satisfy the same Protocol as RemoteWorkerConnection
        # so build_worker_for_mode can return either type uniformly.
        w = InProcessWorker()
        assert isinstance(w, RemoteWorkerConnection)


class TestBuildWorkerForMode:
    @pytest.mark.parametrize(
        "mode",
        [DeployMode.LOCAL, DeployMode.CI_RUNNER, DeployMode.AIR_GAPPED],
    )
    def test_in_process_modes_get_in_process_worker(self, mode: DeployMode):
        # GIVEN an in-process mode
        w = build_worker_for_mode(mode, remote_url=None)
        # THEN the worker is in-process
        assert isinstance(w, InProcessWorker)

    def test_shared_remote_returns_remote_worker(self):
        # GIVEN SHARED_REMOTE mode with a URL
        w = build_worker_for_mode(DeployMode.SHARED_REMOTE, remote_url="http://127.0.0.1:7443")
        # THEN it is a RemoteWorkerConnection (not in-process)
        assert isinstance(w, RemoteWorkerConnection)
        assert not isinstance(w, InProcessWorker)

    def test_hybrid_returns_remote_worker(self):
        # GIVEN HYBRID_EDGE_CLOUD mode
        w = build_worker_for_mode(DeployMode.HYBRID_EDGE_CLOUD, remote_url="http://127.0.0.1:7443")
        # THEN it is a RemoteWorkerConnection
        assert isinstance(w, RemoteWorkerConnection)

    def test_remote_mode_without_url_raises(self):
        # GIVEN a REMOTE mode but no URL configured
        # WHEN build_worker_for_mode runs
        # THEN it refuses with a clear error
        with pytest.raises(ValueError, match="remote_url"):
            build_worker_for_mode(DeployMode.SHARED_REMOTE, remote_url=None)

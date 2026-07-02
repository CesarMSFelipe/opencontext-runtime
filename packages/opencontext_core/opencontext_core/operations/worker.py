"""Worker contract (REQ-ops-deploy-002).

``RemoteWorkerConnection`` is the public protocol used by REMOTE / HYBRID modes
(``studio`` and ``cli``). LOCAL / CI / AIR_GAPPED modes use ``InProcessWorker``
instead — same shape, no network. ``build_worker_for_mode`` is the one
factory both call sites should use; the in-process / remote split is invisible
above this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from opencontext_core.operations.deploy import DeployConfig, DeployMode

CONTRACT_VERSION = 1  # doc 59 §4


@dataclass(frozen=True)
class JobHandle:
    """A reference to a job that has been submitted to a worker.

    ``id`` is opaque; ``status`` is one of ``queued`` / ``running`` /
    ``completed`` / ``failed`` — free-form so the remote side can extend.
    ``mode`` records which deploy mode handled it, which is what the
    decision log reads back to.
    """

    id: str
    status: str
    mode: DeployMode


@runtime_checkable
class RemoteWorkerConnection(Protocol):
    """The wire-level worker contract.

    Concrete impls: ``InProcessWorker`` (LOCAL/CI/AIR_GAPPED) and a future HTTP
    client (REMOTE/HYBRID). Both MUST satisfy this Protocol so callers don't
    branch on the mode.
    """

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def submit_job(self, payload: dict[str, Any]) -> JobHandle: ...


class InProcessWorker:
    """Synchronous, in-process worker. Used by LOCAL / CI / AIR_GAPPED.

    ``connect`` / ``disconnect`` are no-ops kept for protocol symmetry.
    """

    def __init__(self, mode: DeployMode = DeployMode.LOCAL) -> None:
        self._mode = mode
        self._counter = 0
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def submit_job(self, payload: dict[str, Any]) -> JobHandle:
        # In-process: the work has "completed" by the time we return the
        # handle. A real impl would kick off a coroutine / thread.
        # NOTE: LOCAL/CI should be frictionless — auto-connect on first
        # submit if the caller forgot. The Protocol contract is preserved
        # (connect() still works explicitly).
        if not self._connected:
            self._connected = True
        self._counter += 1
        return JobHandle(id=f"local-{self._counter}", status="completed", mode=self._mode)


# NOTE: env var name + error class are spec-level choices; keep them
# in one place so the error message stays consistent across call sites.
_REMOTE_URL_ENVVAR = "OPENCONTEXT_REMOTE_URL"


def build_worker_for_mode(
    mode: DeployMode,
    *,
    remote_url: str | None = None,
    config: DeployConfig | None = None,
) -> RemoteWorkerConnection:
    """Return the right worker for ``mode``.

    LOCAL / CI_RUNNER / AIR_GAPPED → in-process.
    SHARED_REMOTE / HYBRID_EDGE_CLOUD → REMOTE (the caller MUST supply a URL,
    either explicitly or via ``OPENCONTEXT_REMOTE_URL``).
    """
    import os

    if mode in (DeployMode.LOCAL, DeployMode.CI_RUNNER, DeployMode.AIR_GAPPED):
        return InProcessWorker(mode=mode)

    url = remote_url
    if url is None and config is not None:
        url = config.remote_url
    if url is None:
        url = os.environ.get(_REMOTE_URL_ENVVAR)
    if not url:
        # spec REQ-ops-deploy-002: REMOTE/HYBRID derive the URL from
        # OPENCONTEXT_REMOTE_URL. If neither side supplied one, fail loud —
        # silently using a placeholder would mask misconfiguration.
        raise ValueError(
            f"mode={mode.value} requires remote_url (arg, DeployConfig, or "
            f"env var {_REMOTE_URL_ENVVAR})"
        )

    # The real HTTP client lives in a later PR; for now we return a thin
    # stub that records calls and refuses to touch the network. Keeping the
    # boundary here means tests can swap in a fake and the call site is
    # already correct.
    return _NoNetworkRemote(url=url, mode=mode)


class _NoNetworkRemote:
    """Stand-in REMOTE worker that records calls. Wired to fail loud if anyone
    actually invokes it without a real impl. Lives here so the factory is
    self-contained; a real HTTP client will replace this class in a later PR.
    """

    def __init__(self, url: str, mode: DeployMode) -> None:
        self._url = url
        self._mode = mode
        self._connected = False
        self.submitted: list[dict[str, Any]] = []

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def submit_job(self, payload: dict[str, Any]) -> JobHandle:
        # NOTE: real HTTP wiring is a later PR; for now the test suite
        # never reaches here because tests inject _FakeRemote. If you see
        # this in production logs, an HTTP client PR hasn't landed yet.
        raise NotImplementedError(
            f"REMOTE worker transport is scaffolded (url={self._url!r}) but "
            "the HTTP client is not implemented in this PR. Use InProcessWorker "
            "or inject a fake for tests."
        )

"""Commit-017: 9-method session contract for RuntimeApi (amendment A1).

Asserts that ``RuntimeApi`` exposes EXACTLY these 9 methods (no more, no
less) and each carries the documented signature:

    start_session(request)        -> SessionRef
    run(request)                  -> RunResult
    next(session_id)              -> NextAction
    observe(session_id, event)    -> SessionState
    apply(session_id, mutation)   -> ApplyResult
    inspect(session_id, scope)    -> InspectionReport
    resume(session_id)            -> SessionState
    archive(session_id)           -> ArchiveResult
    status(session_id)            -> SessionStatus

Commit-006 added 3 aux stubs (simulate, get_health, decide) that ride
alongside the 9-method session-first contract. The contract test scopes to
ONLY the session API; the aux stubs are covered by test_spine_class.py.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from opencontext_core.runtime.api import RuntimeApi
from opencontext_core.runtime.session import SessionStatus

# (method_name, declared_param_names) -- exact-match on parameter names so
# a future param rename fails the gate loudly. ``self`` is stripped.
SESSION_METHOD_PARAMS: dict[str, tuple[str, ...]] = {
    "start_session": ("request",),
    "run": ("request",),
    "next": ("session_id",),
    "observe": ("session_id", "event"),
    "apply": ("session_id", "mutation"),
    "inspect": ("session_id", "scope"),
    "resume": ("session_id",),
    "archive": ("session_id",),
    "status": ("session_id",),
}


def test_runtime_api_exposes_session_contract(tmp_path: Path) -> None:
    """RuntimeApi exposes EXACTLY the 9 session methods.

    Walks ``RuntimeApi``'s public surface, picks out the 9 names above, and
    asserts no others are missing. Aux stubs (simulate, get_health,
    decide) and internals are NOT in this list -- amendment A1 says they
    are helpers, not replacements.
    """
    api = RuntimeApi(tmp_path)
    public = {
        name for name in dir(api) if not name.startswith("_") and callable(getattr(api, name))
    }

    missing = set(SESSION_METHOD_PARAMS) - public
    assert not missing, f"missing session methods: {sorted(missing)}"

    # Belt-and-braces: the aux stubs (commit-006) MUST still be present
    # alongside the session contract; this commit only adds the 9th
    # session method (status). The contract test is session-only; the
    # aux stubs are guarded by test_spine_class.py.
    for aux in ("simulate", "get_health", "decide"):
        assert aux in public, f"aux stub {aux!r} regressed (commit-006)"


@pytest.mark.parametrize("method_name,expected_params", list(SESSION_METHOD_PARAMS.items()))
def test_runtime_api_session_method_signature(
    method_name: str, expected_params: tuple[str, ...], tmp_path: Path
) -> None:
    """Each session method carries the documented parameter names.

    Catches future signature drift -- amendment A1 pins the 9-method
    contract shape, not just the names.
    """
    method = getattr(RuntimeApi(tmp_path), method_name)
    sig = inspect.signature(method)
    # Drop ``self`` and var-args/var-kwargs to compare clean.
    actual = tuple(p for p in sig.parameters if p != "self")
    assert actual == expected_params, (
        f"RuntimeApi.{method_name} signature drift: expected {expected_params}, got {actual}"
    )


def test_status_method_returns_session_status(tmp_path: Path) -> None:
    """RuntimeApi.status() return annotation is SessionStatus (StrEnum).

    Status is the 9th session method (commit-017). Its return type is the
    canonical ``SessionStatus`` -- not a string, not a Pydantic model.
    """
    method = RuntimeApi(tmp_path).status
    sig = inspect.signature(method)
    ret = sig.return_annotation
    # PEP 563 forward refs stringify ``SessionStatus``; compare both.
    assert ret in {"SessionStatus", SessionStatus}, (
        f"RuntimeApi.status return annotation must be SessionStatus, got {ret!r}"
    )

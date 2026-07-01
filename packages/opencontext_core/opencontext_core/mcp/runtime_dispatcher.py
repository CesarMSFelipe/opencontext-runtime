"""MCP runtime.* dispatcher (commit-008 / amendment A1).

Exposes the 9 session methods of :class:`~opencontext_core.runtime.api.RuntimeApi`
as MCP tools. The dispatcher is gated by
``compat.is_migrated_flag("mcp-runtime")``:

* flag off  -> ``registered_tools()`` returns the legacy tool set (no
  ``runtime.*`` entries);
* flag on   -> exactly the 9 session tools are registered, one per
  RuntimeApi method.

Amendment A1 forbids ``runtime.run_workflow`` -- the 9-method session-first
contract is the only shape on the wire. Routing is a thin pass-through:
the dispatcher builds the request DTOs from the tool input dict and
delegates to the API method.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import opencontext_core.compat as _compat_mod


def _is_migrated_flag(flag: str) -> bool:
    """Late-bound lookup so tests can patch ``opencontext_core.compat.is_migrated_flag``."""
    return _compat_mod.is_migrated_flag(flag)


# Tool name -> (RuntimeApi method name, request-builder). The builders
# convert a flat dict input into the Pydantic request DTO expected by
# RuntimeApi. ``None`` means "no request DTO, just pass session_id".
_SESSION_TOOLS: dict[str, tuple[str, Callable[[dict[str, Any]], Any]]] = {}


def _build_start_session(payload: dict[str, Any]) -> Any:
    from opencontext_core.runtime.api import StartSessionRequest

    return StartSessionRequest(
        task=payload.get("task", ""),
        root=payload.get("root"),
        profile=payload.get("profile", "balanced"),
    )


def _build_run(payload: dict[str, Any]) -> Any:
    from opencontext_core.runtime.api import RunRequest

    return RunRequest(
        session_id=payload["session_id"],
        workflow_id=payload.get("workflow_id", "sdd"),
        task=payload.get("task"),
    )


def _build_observe(payload: dict[str, Any]) -> Any:
    from opencontext_core.runtime.api import RuntimeEventInput

    return RuntimeEventInput(
        type=payload.get("type", "user.note"),
        status=payload.get("status", "ok"),
        message=payload.get("message", ""),
        metadata=payload.get("metadata", {}),
    )


def _build_apply(payload: dict[str, Any]) -> Any:
    from opencontext_core.runtime.api import MutationRequest

    return MutationRequest(
        kind=payload.get("kind", "edit"),
        payload=payload.get("payload", {}),
    )


def _build_inspect(payload: dict[str, Any]) -> Any:
    from opencontext_core.runtime.api import InspectionScope

    raw = payload.get("scope", "session")
    try:
        scope = InspectionScope(raw)
    except ValueError:
        scope = InspectionScope.session
    return scope


_SESSION_TOOLS.update(
    {
        "runtime.start_session": ("start_session", _build_start_session),
        "runtime.run": ("run", _build_run),
        "runtime.next": ("next", None),
        "runtime.observe": ("observe", _build_observe),
        "runtime.apply": ("apply", _build_apply),
        "runtime.inspect": ("inspect", _build_inspect),
        "runtime.resume": ("resume", None),
        "runtime.archive": ("archive", None),
        "runtime.status": ("status", None),
    }
)


def registered_tools() -> list[str]:
    """Return the list of MCP tool names currently registered.

    When ``mcp-runtime`` is off, the legacy tool set is returned (no
    ``runtime.*`` entries). When the flag is on, the 9 session tools
    are returned -- and ONLY those 9.
    """
    if not _is_migrated_flag("mcp-runtime"):
        # Legacy mode: no session tools. (The existing dispatch_mcp_run
        # path remains the OC Flow entry; this dispatcher is spine-only.)
        return []
    return sorted(_SESSION_TOOLS.keys())


def handle_tool_call(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a ``runtime.*`` tool call to the matching RuntimeApi method.

    Returns a dict projection of the API result. ``name`` MUST be in
    :func:`registered_tools` -- the caller is expected to gate on the
    flag before reaching here.
    """
    if not _is_migrated_flag("mcp-runtime"):
        raise RuntimeError(
            "mcp-runtime flag is off; the runtime.* dispatcher is disabled"
        )
    if name not in _SESSION_TOOLS:
        raise KeyError(f"unknown MCP runtime tool: {name!r}")
    method_name, builder = _SESSION_TOOLS[name]

    # Lazy import so the dispatcher module itself never pulls in the
    # full RuntimeApi (and its request DTOs) unless the flag is on.
    from opencontext_core.runtime.api import RuntimeApi

    api = RuntimeApi(payload.get("root") or ".")
    method = getattr(api, method_name)
    if builder is None:
        # 1-arg method (session_id only).
        result = method(payload["session_id"])
    else:
        request = builder(payload)
        result = method(request)

    # Project the result to a dict for the MCP wire format. Pydantic
    # models expose .model_dump; everything else is used as-is.
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return result if isinstance(result, dict) else {"result": result}
"""ST1/ST2/ST3: v2 endpoints serve real state, single redaction, single factory.

RED tests written before implementation. These must fail until the production
code changes are applied.
"""

from __future__ import annotations

import json
import uuid
import warnings
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers — seed minimal project state
# ---------------------------------------------------------------------------


def _seed_session(root: Path, task: str = "test task") -> str:
    """Create a real RuntimeSession and return session_id."""
    from opencontext_core.runtime.session import RuntimeSession
    from opencontext_core.runtime.session_store import SessionStore

    sid = str(uuid.uuid4())
    session = RuntimeSession(session_id=sid, root=str(root), task=task, profile="default")
    SessionStore(root).create_session(session)
    return sid


def _add_decision(root: Path, sid: str, decision_id: str, rationale: str) -> None:
    """Write a run.json with a single decision entry under *sid*."""
    from opencontext_core.paths import StorageMode, resolve_workspace_path

    run_dir = (
        resolve_workspace_path(root, StorageMode.local) / "sessions" / sid / "runs" / "run-001"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "decision_log": {
                    "entries": [
                        {
                            "id": decision_id,
                            "kind": "architecture",
                            "chosen": "option-a",
                            "rationale": rationale,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def _add_context_report(root: Path, sid: str, used_tokens: int, total_budget: int) -> None:
    """Write a context-report.json for *sid* into the session's real directory.

    ``SessionStore`` is mode-aware (``paths.execution_state.sessions_root``),
    so the report must land next to the session it created — pinning the
    legacy in-repo path here breaks in user mode where that session tree is
    never created (execution-state migration).
    """
    from opencontext_core.paths import execution_state

    session_dir = execution_state.sessions_root(root) / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "token_budget": total_budget,
        "layers": [{"name": "pack", "tokens_used": used_tokens, "token_budget": total_budget}],
        "evidence_refs": ["ref-a", "ref-b"],
        "omissions": ["omit-x"],
    }
    (session_dir / "context-report.json").write_text(json.dumps(report), encoding="utf-8")


# ---------------------------------------------------------------------------
# ST1 — v2 endpoints serve real state via StudioReader
# ---------------------------------------------------------------------------


def test_v2_no_stub_values_in_default_empty_project(tmp_path: Path) -> None:
    """All endpoints with an empty project must not return 'stub' in any field."""
    from fastapi.testclient import TestClient
    from opencontext_studio.server_v2 import create_v2_app

    # RED: create_v2_app does not yet accept a root parameter.
    app = create_v2_app(root=tmp_path)
    client = TestClient(app)

    stubs_found: list[str] = []
    for path in (
        "/api/v2/health",
        "/api/v2/brain_state",
        "/api/v2/capability_graph",
        "/api/v2/context_budget",
        "/api/v2/cache_metrics",
        "/api/v2/learning_candidates",
    ):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        body_str = json.dumps(resp.json())
        if '"stub"' in body_str or "'stub'" in body_str:
            stubs_found.append(path)
    assert not stubs_found, f"'stub' literal found in responses for: {stubs_found}"


def test_v2_decision_log_returns_real_rationale(tmp_path: Path) -> None:
    """Seeded decision rationale must appear in /api/v2/decision_log/{id}."""
    from fastapi.testclient import TestClient
    from opencontext_studio.server_v2 import create_v2_app

    sid = _seed_session(tmp_path)
    _add_decision(tmp_path, sid, "d-real-001", "hexagonal over layered for testability")

    # RED: create_v2_app does not yet accept root.
    app = create_v2_app(root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/v2/decision_log/d-real-001")
    assert resp.status_code == 200
    body = resp.json()
    # The rationale must come from the real decision, not be "stub".
    assert body.get("rationale") == "hexagonal over layered for testability"
    assert "stub" not in json.dumps(body)


def test_v2_context_budget_returns_real_token_counts(tmp_path: Path) -> None:
    """Seeded context report token counts must appear in /api/v2/context_budget."""
    from fastapi.testclient import TestClient
    from opencontext_studio.server_v2 import create_v2_app

    sid = _seed_session(tmp_path, task="budget test task")
    _add_context_report(tmp_path, sid, used_tokens=1234, total_budget=8192)

    app = create_v2_app(root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/v2/context_budget")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("used_tokens") == 1234
    assert body.get("available_tokens") == 8192 - 1234
    assert "stub" not in json.dumps(body)


def test_v2_unknown_decision_id_returns_unavailable(tmp_path: Path) -> None:
    """A decision_id that does not exist should return available=False, not stub."""
    from fastapi.testclient import TestClient
    from opencontext_studio.server_v2 import create_v2_app

    app = create_v2_app(root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/v2/decision_log/no-such-id")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("available") is False
    assert body.get("rationale") is None  # schema key present but null when not found
    assert "stub" not in json.dumps(body)


# ---------------------------------------------------------------------------
# ST2 — single redaction path (SinkGuard; content-aware, not key-name only)
# ---------------------------------------------------------------------------


def test_v2_secret_in_rationale_is_masked(tmp_path: Path) -> None:
    """An AWS-key-shaped secret inside a 'rationale' field (not a secret key name)
    must be redacted by SinkGuard pattern matching — not survive the old key-name mask()."""
    from fastapi.testclient import TestClient
    from opencontext_studio.server_v2 import create_v2_app

    # AWS key pattern — SinkGuard detects this by content, mask() misses it.
    secret = "AKIAIOSFODNN7EXAMPLE"
    sid = _seed_session(tmp_path, task="deploy project")
    _add_decision(tmp_path, sid, "d-sec", f"we used {secret} to authenticate")

    app = create_v2_app(root=tmp_path)
    client = TestClient(app)

    resp = client.get("/api/v2/decision_log/d-sec")
    assert resp.status_code == 200
    body_str = json.dumps(resp.json())
    # RED: mask() only checks key names — 'rationale' is not in _MASK_KEYS — so
    # the secret leaks until we switch to redact_value() / SinkGuard.
    assert secret not in body_str, f"Secret leaked through redaction: {body_str[:200]}"


def test_v2_mask_delegates_to_sink_guard() -> None:
    """opencontext_studio.redaction.mask() must delegate to core redact_value.

    Proof: a string containing an AWS key pattern must be redacted even when the
    dict key is not in the legacy _MASK_KEYS set.
    """
    from opencontext_studio.redaction import mask

    aws_key = "AKIAIOSFODNN7EXAMPLE"
    result = mask({"rationale": f"used {aws_key} for auth"})
    # RED: current mask() does not check content, so aws_key survives.
    assert aws_key not in json.dumps(result), (
        "mask() must delegate to SinkGuard so content-based secrets are caught"
    )


# ---------------------------------------------------------------------------
# ST3 — retire duplicate core FastAPI app (single factory invariant)
# ---------------------------------------------------------------------------


def test_create_app_and_create_v2_app_are_same_factory_or_shim_warns() -> None:
    """Importing create_app from core must yield the same factory as create_v2_app
    OR emit a DeprecationWarning — guaranteeing exactly one real app factory."""
    from opencontext_studio.server_v2 import create_v2_app

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        from opencontext_core.studio.app import create_app

        create_app()

    is_same_factory = create_app is create_v2_app
    has_deprecation = any(issubclass(x.category, DeprecationWarning) for x in w)

    # RED: currently create_app is a different real factory with its own routes.
    assert is_same_factory or has_deprecation, (
        "create_app must be an alias for create_v2_app or emit DeprecationWarning; "
        "two real FastAPI app factories must not coexist"
    )

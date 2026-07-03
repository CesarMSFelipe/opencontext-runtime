"""Studio read-only / headless invariants (PR-014 — SPEC-STU-014-11, -12).

Asserts the read-only invariant structurally (no write methods, no mutating
routes, redaction applied) and that the runtime imports/dispatches headless
with Studio absent from the default path.

After the ST3 consolidation, ``opencontext_core.studio.app.create_app`` is a
deprecation shim that delegates to ``opencontext_studio.server_v2.create_v2_app``.
Tests here verify invariants through the v2 surface.
"""

from __future__ import annotations

import json
import uuid
import warnings
from pathlib import Path

from fastapi.testclient import TestClient

from opencontext_core.oc_new.models import ChangeIdentity, OcNewRunState, PhaseState
from opencontext_core.oc_new.store import OcNewStore
from opencontext_core.studio.reader import StudioReader

_WRITE_VERBS = (
    "save",
    "write",
    "delete",
    "mutate",
    "update",
    "create",
    "set_",
    "persist",
    "remove",
)
_MUTATING_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


def _seed_run(root: Path, task: str = "secret task") -> str:
    store = OcNewStore(root)
    ident = ChangeIdentity.from_task(task)
    store.save(
        OcNewRunState(
            identity=ident,
            task=task,
            phases=[PhaseState(name="explore", status="passed")],
            current_phase="explore",
        )
    )
    return ident.run_id


def _seed_session_with_decision(root: Path, decision_id: str, rationale: str) -> str:
    """Create a RuntimeSession with a single decision entry, return session_id."""
    from opencontext_core.paths import StorageMode, resolve_workspace_path
    from opencontext_core.runtime.session import RuntimeSession
    from opencontext_core.runtime.session_store import SessionStore

    sid = str(uuid.uuid4())
    session = RuntimeSession(session_id=sid, root=str(root), task="test", profile="default")
    SessionStore(root).create_session(session)

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
    return sid


def test_reader_exposes_no_write_method() -> None:
    public = [m for m in dir(StudioReader) if not m.startswith("_")]
    offenders = [m for m in public if any(verb in m.lower() for verb in _WRITE_VERBS)]
    assert offenders == [], f"StudioReader must be observe-only; found: {offenders}"


def test_app_route_table_is_get_only(tmp_path: Path) -> None:
    """The v2 app (returned by the create_app shim) exposes only GET routes."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from opencontext_core.studio.app import create_app

        app = create_app(tmp_path)

    methods: set[str] = set()
    for route in app.routes:
        methods |= getattr(route, "methods", set()) or set()
    assert not (methods & _MUTATING_METHODS), f"Studio must expose no mutating route: {methods}"


def test_reader_does_not_create_opencontext_dir(tmp_path: Path) -> None:
    """Constructing the reader and listing an empty project writes nothing."""
    reader = StudioReader(tmp_path)
    assert reader.list_sessions() == []
    assert not (tmp_path / ".opencontext").exists()


def test_secret_redacted_before_display(tmp_path: Path) -> None:
    """An AWS-key-shaped secret in a decision rationale must be masked in API response."""
    from opencontext_studio.server_v2 import create_v2_app

    secret = "AKIAIOSFODNN7EXAMPLE"
    decision_id = "d-secret-redact"
    _seed_session_with_decision(tmp_path, decision_id, rationale=f"deploy with {secret}")
    client = TestClient(create_v2_app(root=tmp_path))
    resp = client.get(f"/api/v2/decision_log/{decision_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    serialized = json.dumps(body)
    assert secret not in serialized, f"Secret leaked in: {serialized[:200]}"
    assert "REDACTED" in serialized.upper(), "Expected a REDACTED marker in response"


def test_api_endpoints_serve(tmp_path: Path) -> None:
    """v2 endpoints return 200 with expected top-level keys."""
    from opencontext_studio.server_v2 import create_v2_app

    # Seed a run so list_sessions returns something.
    _seed_run(tmp_path, task="plain task")
    client = TestClient(create_v2_app(root=tmp_path))
    assert client.get("/api/v2/health").json()["status"] == "ok"
    assert client.get("/api/v2/capability_graph").status_code == 200
    assert client.get("/api/v2/brain_state").status_code == 200
    # Unknown v2 route should 404.
    assert client.get("/api/v2/unknown-view-xyz").status_code == 404


def test_runtime_imports_headless_without_studio() -> None:
    """Importing the runtime/CLI and the Studio data layer must NOT pull in the
    FastAPI web shell. Run in a clean subprocess so a sibling test that imported
    ``studio.app`` cannot pollute ``sys.modules`` (SPEC-STU-014-12)."""
    import subprocess
    import sys

    code = (
        "import opencontext_core, opencontext_cli.main, opencontext_core.studio, sys; "
        "assert 'opencontext_core.studio.app' not in sys.modules; "
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_studio_absent_from_default_dispatch() -> None:
    """Bare ``opencontext`` (no command) never routes to Studio."""
    import inspect

    from opencontext_cli import main

    source = inspect.getsource(main._dispatch)
    none_branch = source.split("if command is None:", 1)[1].split("return", 1)[0]
    assert "studio" not in none_branch.lower()


def test_create_app_shim_emits_deprecation_warning(tmp_path: Path) -> None:
    """create_app from core must emit DeprecationWarning (shim contract)."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        from opencontext_core.studio.app import create_app

        create_app(tmp_path)

    categories = [x.category for x in w]
    assert DeprecationWarning in categories, (
        "core create_app must warn DeprecationWarning; got: " + str(categories)
    )

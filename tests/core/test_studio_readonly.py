"""Studio read-only / headless invariants (PR-014 — SPEC-STU-014-11, -12).

Asserts the read-only invariant structurally (no write methods, no mutating
routes, redaction applied) and that the runtime imports/dispatches headless with
Studio absent from the default path.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from opencontext_core.oc_new.models import ChangeIdentity, OcNewRunState, PhaseState
from opencontext_core.oc_new.store import OcNewStore
from opencontext_core.studio.app import create_app
from opencontext_core.studio.reader import StudioReader

_WRITE_VERBS = (
    "save", "write", "delete", "mutate", "update", "create", "set_", "persist", "remove",
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


def test_reader_exposes_no_write_method() -> None:
    public = [m for m in dir(StudioReader) if not m.startswith("_")]
    offenders = [m for m in public if any(verb in m.lower() for verb in _WRITE_VERBS)]
    assert offenders == [], f"StudioReader must be observe-only; found: {offenders}"


def test_app_route_table_is_get_only(tmp_path: Path) -> None:
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
    # An AWS-key-shaped secret in the task must be redacted in the API payload.
    secret = "AKIAIOSFODNN7EXAMPLE"
    _seed_run(tmp_path, task=f"deploy with {secret}")
    client = TestClient(create_app(tmp_path))
    body = client.get("/api/sessions").json()
    assert body, "expected at least one session"
    serialized = json.dumps(body)
    assert secret not in serialized
    assert "REDACTED" in serialized


def test_api_endpoints_serve(tmp_path: Path) -> None:
    rid = _seed_run(tmp_path, task="plain task")
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/health").json()["read_only"] is True
    assert client.get(f"/api/sessions/{rid}").json()["id"] == rid
    assert client.get(f"/api/sessions/{rid}/timeline").json()["session_id"] == rid
    assert client.get("/api/capabilities").json()["available"] is True
    assert client.get(f"/api/sessions/{rid}/unknown-view").status_code == 404


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
    # studio is dispatched only under an explicit command guard, never the
    # ``command is None`` default branch (which launches the TUI).
    none_branch = source.split("if command is None:", 1)[1].split("return", 1)[0]
    assert "studio" not in none_branch.lower()

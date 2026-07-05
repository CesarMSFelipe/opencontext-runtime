"""TDD — C9: studio serves v2 by default; fallback to stdlib stub on ImportError.

RED gate: run_studio currently calls the stdlib stub unconditionally. The tests
assert that create_v2_app() is called when server_v2 is importable and that the
fallback triggers on ImportError. Both will fail until studio_cmd.py is updated.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest


def _get_studio_parser() -> argparse.ArgumentParser:
    from opencontext_cli.commands.studio_cmd import add_studio_parser

    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command")
    add_studio_parser(subs)
    return subs._name_parser_map["studio"]


# ---------------------------------------------------------------------------
# /api/v2/health 200 — test the actual app (FastAPI availability check)
# ---------------------------------------------------------------------------


def test_studio_serves_v2_health_endpoint() -> None:
    """create_v2_app() /api/v2/health returns HTTP 200 when FastAPI is present."""
    try:
        from opencontext_studio.server_v2 import create_v2_app
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("opencontext_studio or starlette not installed")

    app = create_v2_app()
    client = TestClient(app)
    resp = client.get("/api/v2/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# run_studio routing — v2 when importable, stub fallback on ImportError
# ---------------------------------------------------------------------------


def test_run_studio_calls_create_v2_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run_studio calls create_v2_app() + uvicorn when server_v2 is importable."""
    calls: list[str] = []

    class FakeServerV2:
        @staticmethod
        def create_v2_app(root: object = ".") -> object:
            calls.append("create_v2_app")
            return object()

    class FakeUvicorn:
        @staticmethod
        def run(app: object, **kw: object) -> None:
            calls.append("uvicorn.run")

    # Inject the fakes before studio_cmd is re-imported inside run_studio
    monkeypatch.setitem(sys.modules, "opencontext_studio.server_v2", FakeServerV2)
    monkeypatch.setitem(sys.modules, "uvicorn", FakeUvicorn)

    # Flush studio_cmd so the try/except block runs fresh with the mocked modules
    for key in list(sys.modules):
        if "studio_cmd" in key:
            del sys.modules[key]

    from opencontext_cli.commands.studio_cmd import run_studio

    run_studio(root=tmp_path, port=9999, no_browser=True)

    assert "create_v2_app" in calls, "create_v2_app was not called"
    assert "uvicorn.run" in calls, "uvicorn.run was not called"


def test_run_studio_fallback_on_import_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_studio calls the stdlib stub serve() when server_v2 raises ImportError."""
    serve_calls: list[dict] = []

    def fake_serve(root: object, *, port: int, open_browser: bool) -> str:
        serve_calls.append({"port": port})
        return f"http://localhost:{port}"

    # Simulate ImportError by putting None in sys.modules
    monkeypatch.setitem(sys.modules, "opencontext_studio.server_v2", None)  # type: ignore[assignment]

    for key in list(sys.modules):
        if "studio_cmd" in key:
            del sys.modules[key]

    import opencontext_core.studio.server as _srv

    monkeypatch.setattr(_srv, "serve", fake_serve)

    from opencontext_cli.commands.studio_cmd import run_studio

    run_studio(root=tmp_path, port=8765, no_browser=True)

    assert serve_calls, "Fallback serve() was not called when server_v2 unavailable"


def test_run_studio_fallback_prints_stderr_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """run_studio must emit a stderr line when falling back to the stdlib stub."""
    monkeypatch.setitem(sys.modules, "opencontext_studio.server_v2", None)  # type: ignore[assignment]

    for key in list(sys.modules):
        if "studio_cmd" in key:
            del sys.modules[key]

    import opencontext_core.studio.server as _srv

    monkeypatch.setattr(
        _srv, "serve", lambda root, *, port, open_browser: f"http://localhost:{port}"
    )

    from opencontext_cli.commands.studio_cmd import run_studio

    run_studio(root=tmp_path, port=8765, no_browser=True)

    err = capsys.readouterr().err
    assert "FastAPI/uvicorn unavailable" in err, f"Expected fallback stderr warning, got: {err!r}"


# ---------------------------------------------------------------------------
# --v2 flag must NOT appear in help
# ---------------------------------------------------------------------------


def test_studio_no_v2_flag_in_help() -> None:
    """--v2 flag must NOT be present in the studio argument parser."""
    studio_parser = _get_studio_parser()
    option_strings = [opt for action in studio_parser._actions for opt in action.option_strings]
    assert "--v2" not in option_strings, f"Unexpected --v2 in studio parser: {option_strings}"


# ---------------------------------------------------------------------------
# P1.1 — GET / returns 200 JSON index with service + endpoint list
# ---------------------------------------------------------------------------


def test_studio_v2_root_returns_200_index() -> None:
    """GET / on the v2 app returns HTTP 200 with service name and endpoint list."""
    try:
        from opencontext_studio.server_v2 import create_v2_app
        from starlette.testclient import TestClient
    except ImportError:
        pytest.skip("opencontext_studio or starlette not installed")

    app = create_v2_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("service") == "opencontext-studio-v2"
    assert isinstance(body.get("endpoints"), list)
    assert len(body["endpoints"]) == 7  # seven /api/v2/* routes

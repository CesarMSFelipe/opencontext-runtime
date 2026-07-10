"""F3a: the MCP server must honor the project's ``./opencontext.yaml``.

``_mcp_serve`` used to build ``OpenContextRuntime(storage_path=...)`` with NO
``config_path``. ``_load_config_or_defaults(None)`` then only checks the literal
``configs/opencontext.yaml`` — never the project-root ``./opencontext.yaml`` — so
a project's config (security mode, gates, memory, harness settings) was silently
ignored by the MCP server.

The fix resolves the project config via ``find_config(Path.cwd())`` and passes it
as ``config_path``. ``find_config`` returns ``Path | None``; ``None`` must keep
today's default behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from opencontext_cli import main as cli_main


class _CapturingRuntime:
    """Records the kwargs ``_mcp_serve`` used to build the runtime."""

    captured: ClassVar[dict[str, Any]] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # storage_path derives a plausible db parent for MCPServer construction.
        type(self).captured = dict(kwargs)
        self.storage_path = Path(kwargs.get("storage_path") or ".")


class _NoopServer:
    """MCPServer stand-in that never starts a transport."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def run(self) -> None:  # pragma: no cover - trivial
        return None

    def close(self) -> None:  # pragma: no cover - trivial
        return None


@pytest.fixture()
def _patched(monkeypatch: pytest.MonkeyPatch) -> None:
    _CapturingRuntime.captured = {}
    monkeypatch.setattr(
        "opencontext_core.runtime.OpenContextRuntime",
        _CapturingRuntime,
    )
    monkeypatch.setattr(
        "opencontext_core.mcp_stdio.MCPServer",
        _NoopServer,
    )


def test_mcp_serve_passes_project_config_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _patched: None
) -> None:
    """With a ``./opencontext.yaml`` present in cwd, ``_mcp_serve`` builds the
    runtime with ``config_path`` pointing at that file."""
    cfg = tmp_path / "opencontext.yaml"
    cfg.write_text("project:\n  name: demo\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    cli_main._mcp_serve(str(tmp_path / "graph.db"))

    captured = _CapturingRuntime.captured
    assert "config_path" in captured, captured
    assert captured["config_path"] == cfg, captured


def test_mcp_serve_config_path_none_without_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _patched: None
) -> None:
    """With no ``opencontext.yaml`` anywhere up the tree, ``config_path`` is
    ``None`` — preserving today's default-config behavior."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    # ``tmp_path`` lives under /tmp, so ``find_config`` walking up the tree
    # finds no ``opencontext.yaml`` — the genuine "no project config" case.

    cli_main._mcp_serve(str(empty / "graph.db"))

    captured = _CapturingRuntime.captured
    # Either config_path is explicitly None or omitted — both mean "defaults".
    assert captured.get("config_path") is None, captured

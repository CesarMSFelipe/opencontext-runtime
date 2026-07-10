"""F4: document (and pin) the MCP server's storage-location resolution rule.

An MCP server that a host spawns persisted sessions under the XDG user dir
(``~/.local/state/opencontext/...``) instead of the project's ``.opencontext/``
even though ``OPENCONTEXT_STORAGE_MODE=local`` was set in the *parent* env.

Investigation conclusion: this is a LEGITIMATE fallback, not a code defect.

Resolution rule (pinned by these tests):

1. ``_mcp_serve`` builds the runtime with an EXPLICIT ``storage_path``
   (``Path(db_path).parent``). When ``storage_path`` is given, the runtime does
   NOT run the XDG/local resolver — the explicit path wins. So the MCP server
   persists wherever ``db_path`` points.
2. ``db_path`` itself comes from the *outer* CLI runtime's already-resolved
   ``storage_path`` (main.py: ``runtime.storage_path / "context_graph.db"``),
   which DOES honor ``storage.mode`` / ``OPENCONTEXT_STORAGE_MODE`` /
   ``opencontext.yaml`` at the point the ``opencontext mcp`` command runs.

Therefore, when the server lands under XDG it is because the effective storage
mode resolved to ``user`` (the documented default) for that invocation. The
codex incident was the host spawning the MCP subprocess WITHOUT propagating
``OPENCONTEXT_STORAGE_MODE`` into the child process — a host-spawn env issue,
not an OpenContext defect. Artifacts persist fine; only the location differs.

The F3a fix (passing the project ``opencontext.yaml`` as ``config_path``) is the
strictly-better follow-on: a project that declares ``storage.mode: local`` in
its ``opencontext.yaml`` is now read by the MCP-server runtime too.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from opencontext_core.runtime import OpenContextRuntime


def _project_config(root: Path, *, storage_mode: str) -> Path:
    cfg = root / "opencontext.yaml"
    cfg.write_text(
        "project:\n"
        "  name: demo\n"
        "project_index:\n"
        f"  root: {root}\n"
        "storage:\n"
        f"  mode: {storage_mode}\n",
        encoding="utf-8",
    )
    return cfg


def test_explicit_storage_path_wins_over_config_storage_mode() -> None:
    """Rule 1: an explicit ``storage_path`` bypasses the storage resolver.

    Even with ``storage.mode: local`` in config, the runtime persists at the
    explicit path ``_mcp_serve`` gives it — the resolver is never consulted.
    This is why the MCP server's location is decided by ``db_path``, not by a
    second reading of ``storage.mode``.
    """
    tmp = Path(tempfile.mkdtemp())
    proj = tmp / "proj"
    proj.mkdir()
    _project_config(proj, storage_mode="local")
    explicit = proj / ".opencontext"
    explicit.mkdir()

    runtime = OpenContextRuntime(
        config_path=proj / "opencontext.yaml",
        storage_path=explicit,
    )

    assert runtime.storage_path == explicit
    # The config was still read (F3a) — mode is visible even though the
    # explicit storage_path overrides the *location*.
    assert runtime.config.storage.mode == "local"


def test_local_storage_mode_resolves_into_project_when_no_explicit_path() -> None:
    """Rule 2: with NO explicit ``storage_path``, ``storage.mode: local`` puts
    storage inside the project (the resolver runs). This is the mode the outer
    CLI runtime uses to compute the ``db_path`` the MCP server then inherits.
    """
    tmp = Path(tempfile.mkdtemp())
    proj = tmp / "proj"
    proj.mkdir()
    cfg = _project_config(proj, storage_mode="local")

    runtime = OpenContextRuntime(config_path=cfg)  # no storage_path override

    assert runtime.config.storage.mode == "local"
    # local mode keeps storage under the project root, not XDG.
    assert str(proj) in str(runtime.storage_path), runtime.storage_path


def test_user_storage_mode_is_a_valid_persistence_location() -> None:
    """Rule 3 (the incident): ``user`` mode persisting under XDG is legitimate —
    the resolver returns a real, writable path (just not inside the repo)."""
    tmp = Path(tempfile.mkdtemp())
    proj = tmp / "proj"
    proj.mkdir()
    cfg = _project_config(proj, storage_mode="user")

    runtime = OpenContextRuntime(config_path=cfg)  # no storage_path override

    assert runtime.config.storage.mode == "user"
    # A real path is resolved and created — persistence still works, it just
    # lives in the user dir. Not a defect: the documented default.
    assert runtime.storage_path.exists()
    assert str(proj) not in str(runtime.storage_path), runtime.storage_path

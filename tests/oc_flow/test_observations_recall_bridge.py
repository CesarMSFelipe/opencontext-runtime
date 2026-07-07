"""A CLI observation (memory_v2.db) is recalled into an OC Flow run.

Regression for a verification finding: the `opencontext memory v2` store
(memory_v2.db / observations) was disjoint from the in-loop agent store
(memory.db), so a user's `memory v2 save` was never visible to any run. The flow
recall now also folds matching observations into the context envelope. Driven as
a subprocess so it exercises the real user path (save via CLI, then run).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_PKGS = [
    _REPO / "packages" / p
    for p in ("opencontext_core", "opencontext_cli", "opencontext_memory", "opencontext_sdd")
]


def _env(home: Path) -> dict[str, str]:
    entries = [
        str(Path(r).resolve()) for r in os.environ.get("PYTHONPATH", "").split(os.pathsep) if r
    ]
    for pkg in _PKGS:
        if str(pkg) not in entries:
            entries.append(str(pkg))
    return {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "PYTHONPATH": os.pathsep.join(entries),
        "OPENCONTEXT_STORAGE_MODE": "local",
    }


def _oc(args: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", "-m", "opencontext_cli.main", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_cli_observation_is_recalled_into_flow_envelope(tmp_path: Path) -> None:
    if shutil.which("python") is None:
        pytest.skip("python not on PATH")
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()
    (proj / "auth.py").write_text("def authenticate(u, p):\n    return u == p\n", encoding="utf-8")
    env = _env(home)

    saved = _oc(
        [
            "memory",
            "v2",
            "save",
            "--title",
            "Auth rule",
            "--content",
            "authentication must use bcrypt for password hashing",
            "--type",
            "decision",
        ],
        proj,
        env,
    )
    assert saved.returncode == 0, saved.stderr

    run = _oc(
        [
            "run",
            "improve authenticate password hashing",
            "--workflow",
            "oc-flow",
            "--json",
            "--yes",
        ],
        proj,
        env,
    )
    # A mutation task without an executor honestly ends needs_executor -> exit 5
    # (RUN_STATE_CONTRACT); the recall assertion below is what this test is about.
    assert run.returncode in (0, 5), run.stderr

    envelopes = list((proj / ".opencontext").rglob("artifacts/oc-flow/context-envelope.json"))
    assert envelopes, "no context-envelope.json produced"
    body = envelopes[0].read_text(encoding="utf-8")
    assert "bcrypt" in body, "the CLI-saved observation was not recalled into the flow envelope"
    assert "memory:observation" in body

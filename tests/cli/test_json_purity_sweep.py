"""DOD1-DELTAS / MET-PRODUCT: JSON purity sweep over the stable ``--json`` surface.

DOC1 §19 DoD #15 ("no dirty JSON") and DOC2 §29.1 ("JSON parse failures: 0")
are product-wide guarantees, but coverage used to be per-command spot tests —
`knowledge-graph impact --json` shipped a logo+header on stdout for months
because nothing swept the whole surface. This module:

1. enumerates every stable subcommand that registers ``--json`` from the REAL
   parser (source of truth, so a new subcommand cannot dodge the sweep), and
2. invokes each one through the real binary in an isolated workspace,
   asserting stdout is exactly one parseable JSON document — success AND
   documented error paths alike.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess

import pytest
from tests.acceptance.helpers.workspace import Workspace, make_workspace

# ---------------------------------------------------------------------------
# Surface enumeration (in-process, from the real parser)
# ---------------------------------------------------------------------------


def _json_capable_stable_paths() -> set[tuple[str, ...]]:
    """Every stable (sub)command path that registers a ``--json`` flag."""
    from opencontext_cli.contracts.command_registry import COMMAND_MATURITY
    from opencontext_cli.main import _build_parser

    stable = {cmd for cmd, level in COMMAND_MATURITY.items() if level == "stable"}
    paths: set[tuple[str, ...]] = set()

    def walk(parser: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        if any("--json" in (action.option_strings or []) for action in parser._actions):
            paths.add(path)
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                seen: set[int] = set()
                for name, sub in action.choices.items():
                    if id(sub) in seen:
                        continue  # aliases share one parser
                    seen.add(id(sub))
                    walk(sub, (*path, name))

    root = _build_parser()
    for action in root._actions:
        if isinstance(action, argparse._SubParsersAction):
            seen: set[int] = set()
            for name, sub in action.choices.items():
                if name not in stable or id(sub) in seen:
                    continue
                seen.add(id(sub))
                walk(sub, (name,))
    return paths


#: One real invocation per json-capable stable subcommand path. Error-path
#: invocations (unknown run id, missing symbol) are deliberate: --json must
#: yield a parseable document on stdout there too (CLI_CONTRACT error
#: envelope), or an agent's json.loads(stdout) blows up exactly when it needs
#: the error most.
INVOCATIONS: dict[tuple[str, ...], list[str]] = {
    ("version",): ["version", "--json"],
    ("status",): ["status", "--json"],
    ("doctor",): ["doctor", "--json"],
    ("init",): ["init", "--json"],
    ("install",): ["install", ".", "--yes", "--json"],
    ("clean",): ["clean", "--dry-run", "--json"],
    ("index",): ["index", ".", "--json"],
    ("pack",): ["pack", ".", "--query", "fix alpha", "--json"],
    ("run",): ["run", "improve alpha", "--json"],
    ("runs", "list"): ["runs", "list", "--json"],
    ("runs", "show"): ["runs", "show", "no-such-run", "--json"],
    ("runs", "artifacts"): ["runs", "artifacts", "no-such-run", "--json"],
    ("uninstall",): [
        "uninstall",
        "--scope",
        "workspace",
        "--dry-run",
        "--yes",
        "--json",
        "--root",
        ".",
    ],
    ("config", "show"): ["config", "show", "--json"],
    ("config", "explain"): ["config", "explain", "--json"],
    ("config", "doctor"): ["config", "doctor", "--json"],
    ("knowledge-graph", "search"): ["knowledge-graph", "search", "alpha", "--json"],
    ("knowledge-graph", "query"): ["knowledge-graph", "query", "alpha", "--json"],
    ("knowledge-graph", "context"): ["knowledge-graph", "context", "fix alpha", "--json"],
    ("knowledge-graph", "callers"): ["knowledge-graph", "callers", "beta", "--json"],
    ("knowledge-graph", "callees"): ["knowledge-graph", "callees", "alpha", "--json"],
    ("knowledge-graph", "impact"): ["knowledge-graph", "impact", "beta", "--json"],
    ("knowledge-graph", "node"): ["knowledge-graph", "node", "alpha", "--json"],
    ("knowledge-graph", "status"): ["knowledge-graph", "status", "--json"],
    ("knowledge-graph", "related-tests"): [
        "knowledge-graph",
        "related-tests",
        "mod.py",
        "--json",
    ],
    ("knowledge-graph", "prune"): ["knowledge-graph", "prune", "--dry-run", "--json"],
    ("knowledge-graph", "explain-pack"): [
        "knowledge-graph",
        "explain-pack",
        "--run",
        "no-such-run",
        "--json",
    ],
    ("knowledge-graph", "trace"): ["knowledge-graph", "trace", "alpha", "beta", "--json"],
    ("sdd", "status"): ["sdd", "status", "--json"],
    ("sdd", "review"): ["sdd", "review", "--json"],
    ("harness", "run"): [
        "harness",
        "run",
        "--workflow",
        "explore-only",
        "--task",
        "map the module",
        "--json",
    ],
    ("harness", "list"): ["harness", "list", "--json"],
    ("harness", "report"): ["harness", "report", "--json"],
    ("memory", "init"): ["memory", "init", "--json"],
    ("memory", "list"): ["memory", "list", "--json"],
    ("memory", "benchmark"): ["memory", "benchmark", "--json"],
}


# ---------------------------------------------------------------------------
# Shared swept workspace (one install+index for the whole sweep)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def oc_bin() -> str:
    resolved = shutil.which("opencontext")
    if not resolved:
        pytest.skip("no opencontext binary on PATH: activate a venv with opencontext installed")
    return resolved


@pytest.fixture(scope="module")
def swept_ws(oc_bin: str, tmp_path_factory: pytest.TempPathFactory) -> Workspace:
    """A tiny installed+indexed project every sweep invocation runs against."""
    ws = make_workspace(tmp_path_factory.mktemp("json-sweep"))
    (ws.root / "mod.py").write_text(
        "def alpha():\n    return beta()\n\n\ndef beta():\n    return 1\n", encoding="utf-8"
    )
    tests_dir = ws.root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_mod.py").write_text(
        "from mod import alpha\n\n\ndef test_alpha():\n    assert alpha() == 1\n",
        encoding="utf-8",
    )
    for argv in (["install", ".", "--yes", "--json"], ["index", ".", "--json"]):
        proc = subprocess.run(
            [oc_bin, *argv],
            cwd=ws.root,
            env=ws.env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert proc.returncode == 0, f"workspace prep failed: {argv}: {proc.stderr[:400]}"
    return ws


def test_every_json_capable_stable_subcommand_is_swept() -> None:
    """MET-PRODUCT: the sweep covers the ENTIRE stable --json surface.

    §29.1 "JSON parse failures: 0" is only a measured metric if every
    json-capable stable subcommand has a sweep invocation. Registering a new
    --json flag on a stable command without adding it here fails this test.
    """
    surface = _json_capable_stable_paths()
    missing = sorted(" ".join(path) for path in surface - set(INVOCATIONS))
    stale = sorted(" ".join(path) for path in set(INVOCATIONS) - surface)
    assert not missing, f"stable --json subcommands missing a sweep invocation: {missing}"
    assert not stale, f"sweep invocations for subcommands no longer on the surface: {stale}"


@pytest.mark.parametrize(
    "argv",
    [pytest.param(argv, id=" ".join(path)) for path, argv in sorted(INVOCATIONS.items())],
)
def test_stable_json_stdout_is_pure(oc_bin: str, swept_ws: Workspace, argv: list[str]) -> None:
    """DOD1-DELTAS: every stable subcommand under --json emits exactly one
    parseable JSON document on stdout (DoD #15 "no dirty JSON"), on success
    and on documented error paths alike."""
    proc = subprocess.run(
        [oc_bin, *argv],
        cwd=swept_ws.root,
        env=swept_ws.env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.stdout.strip(), (
        f"--json produced empty stdout (exit={proc.returncode}); the JSON document "
        f"(or error envelope) must be on stdout. argv={argv} stderr={proc.stderr[:400]!r}"
    )
    try:
        json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"dirty JSON on stdout for {argv} (exit={proc.returncode}): {exc}\n"
            f"stdout[:600]={proc.stdout[:600]!r}"
        ) from None

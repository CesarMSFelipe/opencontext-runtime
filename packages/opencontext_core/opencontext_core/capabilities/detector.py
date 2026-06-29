"""Build the live Capability Graph by REUSING existing detection (CP-004..CP-006).

The detector does not reimplement detection. It folds three existing sources into
typed ``CapabilityNode``s:

* ``sdd_runtime.detect_test_capabilities`` — test/lint/type tooling (CP-001).
* ``providers.detect.detect_provider`` — the ambient LLM provider.
* ``agent_installer.AgentInstaller.detect_installed_agents`` — agent clients
  (the same detection ``doctor/component_checks.py`` uses).

It then wires dependency edges (e.g. ``strict_harness -> pytest``) so the graph
exposes readiness, not just a flat list.

Layering (doc 58): L3. It reads lower/leaf detection utilities only and is never
imported by them; upper layers receive the built graph by injection.
"""

from __future__ import annotations

import os
from pathlib import Path

from opencontext_core.capabilities.graph import CapabilityGraph, CapabilityKind, CapabilityNode

# Synthetic capability ids the graph derives from raw tooling facts. Kept as
# constants so PR-003 (required_capabilities) and the Brain reference one id scheme.
STRICT_HARNESS = "strict_harness"

# Map a detected TestCapability.scope onto a CapabilityNode.kind.
_SCOPE_KIND: dict[str, CapabilityKind] = {
    "focused": "test",
    "broad": "test",
    "e2e": "test",
    "lint": "lint",
    "type": "type",
}


def _kind_for_scope(scope: str) -> CapabilityKind:
    return _SCOPE_KIND.get(scope, "test")


def build_capability_graph(root: Path | str = ".") -> CapabilityGraph:
    """Build the live ``CapabilityGraph`` for ``root`` from existing detection.

    Never raises on a missing/odd environment: detection sources that fail are
    skipped so ``doctor`` and a first run always get a usable graph.
    """
    nodes: list[CapabilityNode] = []

    nodes.extend(_tooling_nodes(root))
    # Manifest detection (above) is gated on pyproject.toml/pytest.ini/go.mod/etc.
    # A real small project often has only `.py` and `test_*.py` files and no such
    # manifest, which would leave the graph empty. Supplement with direct
    # source-file evidence so genuine capabilities (language, test runner, VCS)
    # are reported. First-wins by id keeps manifest evidence authoritative.
    existing_ids = {node.id for node in nodes}
    nodes.extend(_source_evidence_nodes(root, existing_ids))
    provider_node = _provider_node()
    if provider_node is not None:
        nodes.append(provider_node)
    nodes.extend(_agent_nodes(root))
    nodes.append(_strict_harness_node())

    return CapabilityGraph(nodes=nodes)


# Directories that never hold a project's own source and would only add noise (or
# cost) to the evidence scan. Pruned so detection stays fast and honest.
_IGNORE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".tox",
        ".nox",
        "build",
        "dist",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".opencontext",
        ".storage",
        "site-packages",
    }
)


def _source_evidence_nodes(root: Path | str, existing_ids: set[str]) -> list[CapabilityNode]:
    """Detect capabilities from source-file evidence the manifest scan misses.

    Honest by construction: a node is added only when a matching file/marker
    actually exists, and ids already produced by manifest detection are skipped
    so their evidence stays authoritative. Nothing is fabricated — a project with
    no python sources gets no python node, one with no tests gets no pytest node.
    """
    base = Path(root)
    nodes: list[CapabilityNode] = []

    first_py, first_test = _scan_python_evidence(base)
    if first_py is not None and "python" not in existing_ids:
        nodes.append(
            CapabilityNode(
                id="python",
                kind="language",
                available=True,
                evidence=f"python source file: {first_py}",
            )
        )
    # `test_*.py` / `*_test.py` are pytest's default discovery patterns, so such a
    # file is genuine evidence the pytest runner applies even without a manifest.
    if first_test is not None and "pytest" not in existing_ids:
        nodes.append(
            CapabilityNode(
                id="pytest",
                kind="test",
                available=True,
                evidence=f"pytest-style test file: {first_test}",
            )
        )

    vcs_node = _vcs_node(base)
    if vcs_node is not None and vcs_node.id not in existing_ids:
        nodes.append(vcs_node)

    return nodes


def _scan_python_evidence(base: Path, *, file_limit: int = 5000) -> tuple[str | None, str | None]:
    """Return (first ``.py`` file, first pytest-style test file), relative to ``base``.

    Walks the tree, pruning vendored/cache directories, and stops early once both
    markers are found or ``file_limit`` files have been seen (so a large tree
    never makes ``doctor`` slow).
    """
    first_py: str | None = None
    first_test: str | None = None
    seen = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for filename in filenames:
            seen += 1
            if seen > file_limit:
                return first_py, first_test
            if not filename.endswith(".py"):
                continue
            rel = _relative(base, Path(dirpath) / filename)
            if first_py is None:
                first_py = rel
            if first_test is None and (
                filename.startswith("test_") or filename.endswith("_test.py")
            ):
                first_test = rel
            if first_py is not None and first_test is not None:
                return first_py, first_test
    return first_py, first_test


def _vcs_node(base: Path) -> CapabilityNode | None:
    """A git VCS capability when the project is a git repo (dir or worktree file)."""
    if (base / ".git").exists():
        return CapabilityNode(
            id="git",
            kind="vcs",
            available=True,
            evidence=".git",
        )
    return None


def _relative(base: Path, path: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def _tooling_nodes(root: Path | str) -> list[CapabilityNode]:
    """Lift ``detect_test_capabilities`` records into typed nodes (no new detection)."""
    from opencontext_core.sdd_runtime import detect_test_capabilities

    nodes: list[CapabilityNode] = []
    try:
        for cap in detect_test_capabilities(root):
            nodes.append(
                CapabilityNode(
                    id=cap.name,
                    kind=_kind_for_scope(cap.scope),
                    available=True,
                    evidence=cap.evidence,
                )
            )
    except Exception:
        return []
    return nodes


def _provider_node() -> CapabilityNode | None:
    """Fold ambient provider detection into a provider capability node."""
    try:
        from opencontext_core.providers.detect import detect_provider

        detected = detect_provider()
    except Exception:
        return None
    # A "fallback"/mock provider means no real provider is available.
    available = detected.source != "fallback"
    return CapabilityNode(
        id=f"provider.{detected.name}",
        kind="provider",
        available=available,
        evidence=f"source={detected.source}; model={detected.model}",
    )


def _agent_nodes(root: Path | str) -> list[CapabilityNode]:
    """Reuse the agent installer's detection (same source as doctor component checks)."""
    try:
        from opencontext_core.agent_installer import AgentInstaller

        installer = AgentInstaller(root)
        detected = installer.detect_installed_agents()
    except Exception:
        return []
    return [
        CapabilityNode(
            id=f"agent.{agent.value}",
            kind="agent",
            available=True,
            evidence="agent installer detection",
        )
        for agent in detected
    ]


def _strict_harness_node() -> CapabilityNode:
    """A strict harness capability that depends on a focused test runner (CP-005).

    The node itself is "available" (the harness feature exists), but it is only
    *ready* when its dependency (``pytest``) is ready — so ``is_ready`` /
    ``unmet_dependencies`` surface a missing test runner.
    """
    return CapabilityNode(
        id=STRICT_HARNESS,
        kind="harness",
        available=True,
        evidence="depends on a focused test runner",
        depends_on=["pytest"],
    )

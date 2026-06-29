"""doc-58 layering guard — no NEW upward imports (PR-017 Enforcement section).

An ``ast``-based contract over ``packages/opencontext_core/opencontext_core/``: every
EAGER (module-top) import must point DOWN the doc-58 L0-L11 layering, never up.

Two deliberate, documented policies keep this honest rather than noisy:

1. **Eager-only enforcement.** Only module-top imports are checked — those are the
   ones that create import-time cycles. Function-local (lazy) imports are the
   sanctioned cycle-break mechanism doc-58 itself calls for (it says L8↔L10 must go
   "through an injected port, not a direct import"); a lazy import is the pragmatic
   equivalent and is reported separately, not failed.

2. **A frozen baseline (ratchet).** The codebase's ``runtime/`` package is the
   composition root (``OpenContextRuntime`` wires the higher cognitive layers), so
   it legitimately imports upward; this and the other pre-existing upward edges are
   recorded in :data:`ALLOWED_UPWARD` with reasons. The guard FAILS on any upward
   edge NOT in that set — i.e. it blocks *new* upward imports while documenting the
   accepted existing ones (the same ratchet philosophy as ``quality/baseline.py``).

If you add a new upward import you must either remove it, make it lazy with a
``# layering: lazy cycle-break`` rationale, or add it to ``ALLOWED_UPWARD`` with a
reason in review — never silently.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / ("packages/opencontext_core/opencontext_core")

# doc-58 L0-L11. Cross-cutting infra leaves (compat / dx / tools / i18n / errors /
# config / models / …) sit at L0: everyone may import them and they depend only
# downward. memory_usability is a memory-adjacent L4 sibling.
LAYER: dict[str, int] = {
    # L0 contracts / models / ids / cross-cutting infra
    "models": 0,
    "errors": 0,
    "exceptions": 0,
    "state": 0,
    "metrics": 0,
    "i18n": 0,
    "trace": 0,
    "rules": 0,
    "compat": 0,
    "dx": 0,
    "tools": 0,
    "config": 0,
    "user_prefs": 0,
    "prompts": 0,
    # L1 runtime core (composition root in this codebase)
    "runtime": 1,
    # L2 stores & evidence
    "operating_model": 2,
    # L3 governance
    "policy": 3,
    "profiles": 3,
    "capabilities": 3,
    "safety": 3,
    "security": 3,
    "actions": 3,
    # L4 knowledge substrate
    "graph": 4,
    "memory": 4,
    "cache": 4,
    "compression": 4,
    "embeddings": 4,
    "indexing": 4,
    "retrieval": 4,
    "backends": 4,
    "memory_usability": 4,
    # L5 context engine
    "context": 5,
    # L6 registries
    "registries": 6,
    "personas": 6,
    "skills": 6,
    "harness": 6,
    "workflows": 6,
    "workflow": 6,
    "workflow_packs": 6,
    "tdd": 6,
    # L7 providers
    "providers": 7,
    "llm": 7,
    "adapters": 7,
    # L8 orchestration
    "planning": 8,
    "agents": 8,
    "agentic": 8,
    # L9 workflows
    "sdd": 9,
    "oc_flow": 9,
    "oc_new": 9,
    "openspec": 9,
    "mutation": 9,
    # L10 runtime intelligence
    "runtime_intelligence": 10,
    "evaluation": 10,
    "quality": 10,
    "learning": 10,
    "optimization": 10,
    "economy": 10,
    "verify": 10,
    # L11 interfaces
    "mcp": 11,
    "studio": 11,
    "plugins": 11,
    "marketplace": 11,
    "configurator": 11,
    "setup": 11,
    "onboarding": 11,
    "doctor": 11,
    "hooks": 11,
    "project": 11,
    "workspace": 11,
}

# Top-level *.py modules that are config/setup orchestration glue, not layered
# packages; skip them as import sources.
SKIP_SRC: frozenset[str] = frozenset(
    {
        "config",
        "config_doctor",
        "config_profiles",
        "config_resolver",
        "config_snapshot",
        "config_sync",
        "sdd_profiles",
        "sdd_runtime",
        "wizard",
        "agent_installer",
        "backup",
        "install_manager",
        "mcp_stdio",
        "plugin_system",
        "tree_sitter_grammars",
        "update",
        "verification",
        "explain",
    }
)

# Frozen baseline of pre-existing EAGER upward edges (src_top -> dst_top), each with
# a documented reason. New upward edges NOT listed here fail the guard.
ALLOWED_UPWARD: dict[tuple[str, str], str] = {
    # runtime/ is the composition root: OpenContextRuntime wires the higher
    # cognitive layers (context/indexing/embeddings/providers/...). Book L1 is a
    # narrow core; this repo's runtime/ legitimately composes upward.
    ("runtime", "agentic"): "composition root wires orchestration",
    ("runtime", "context"): "composition root wires the context engine",
    ("runtime", "embeddings"): "composition root wires embeddings",
    ("runtime", "indexing"): "composition root wires indexing",
    ("runtime", "learning"): "composition root wires learning",
    ("runtime", "llm"): "composition root wires the LLM client",
    ("runtime", "memory"): "composition root wires memory",
    ("runtime", "memory_usability"): "composition root wires memory usability",
    ("runtime", "operating_model"): "composition root wires receipts/evidence",
    ("runtime", "policy"): "composition root wires policy",
    ("runtime", "project"): "composition root reads project manifest",
    ("runtime", "providers"): "composition root wires the provider gateway",
    ("runtime", "retrieval"): "composition root wires retrieval",
    ("runtime", "safety"): "composition root wires safety/redaction",
    ("runtime", "workflow"): "composition root wires workflow phase results",
    ("runtime", "workspace"): "composition root wires workspace",
    # L0 contract pieces that physically live in higher-layer packages: runtime.ids
    # exports ID generators (book L0 = Contracts/Models/IDs) and graph.{edges,nodes}
    # export Kind enums (contracts). Conceptually L0; physical relocation deferred.
    ("models", "runtime"): "models import L0 ID generators that live under runtime.ids",
    ("models", "graph"): "models.kg_v2 imports Kind enums (L0 contracts) from graph",
    # Stores/evidence (L2) composing governance + context evidence.
    ("operating_model", "context"): "evidence builder reads context evidence",
    ("operating_model", "providers"): "provider receipts reference provider ids",
    ("operating_model", "safety"): "release scan reuses redaction primitives",
    # Knowledge substrate building context-shaped helpers.
    ("retrieval", "context"): "retrieval emits context-shaped results",
    ("indexing", "context"): "indexing shares context source types",
    ("indexing", "project"): "indexer reads the project manifest",
    ("memory_usability", "context"): "memory usability formats context items",
    # Registries / harness composing orchestration + intelligence (definitions).
    ("context", "agentic"): "context substrate shared with agentic builder",
    ("context", "harness"): "context references harness gate types",
    ("harness", "agentic"): "harness phases drive the agentic spine",
    ("harness", "agents"): "harness phases invoke agent executors",
    ("personas", "configurator"): "persona wiring references configurator defaults",
    ("personas", "oc_new"): "persona flow references oc-new phase ids",
    ("workflow", "llm"): "phase result references llm usage types",
    ("workflow", "oc_new"): "phase result references oc-new flow",
    # Misc declared seams.
    ("agents", "mutation"): "agent executor applies mutations",
    ("planning", "verify"): "planning references verify gate ids",
    ("tdd", "openspec"): "tdd bridges the openspec seam",
    # PR-017: the release gate composes the L10 benchmark runner + GateStatus, but
    # lives with the other release tooling (ai_leak/evidence) under operating_model.
    ("operating_model", "evaluation"): "release_gate composes the L10 benchmark runner",
    ("dx", "context"): "console renders context items",
    ("dx", "indexing"): "console renders index status",
    ("rules", "context"): "rules reference context source types",
    ("rules", "retrieval"): "rules reference retrieval results",
    ("tools", "safety"): "tool wrappers apply safety policy",
}


def _top_of(path: Path) -> str:
    rel = path.relative_to(ROOT)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def _imported_tops(node: ast.AST) -> list[str]:
    out: list[str] = []
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        if mod.startswith("opencontext_core.") and node.level == 0:
            out.append(mod.split(".")[1])
    elif isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.startswith("opencontext_core."):
                out.append(alias.name.split(".")[1])
    return out


def _module_top_imports(py: Path) -> list[str]:
    """Top-of-module (eager runtime) opencontext_core imports for one file.

    Imports nested under ``if TYPE_CHECKING:`` or inside functions are excluded —
    they create no runtime cycle, matching the guard's eager-only policy.
    """
    tree = ast.parse(py.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.extend(_imported_tops(node))
    return out


def _eager_upward_edges() -> dict[tuple[str, str], list[str]]:
    """Map every eager upward edge (src_top, dst_top) -> example source files."""
    edges: dict[tuple[str, str], list[str]] = {}
    for py in ROOT.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        src = _top_of(py)
        if src in SKIP_SRC or src not in LAYER:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        top_node_ids = {id(n) for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))}
        for node in ast.walk(tree):
            if id(node) not in top_node_ids:
                continue
            for dst in _imported_tops(node):
                if dst not in LAYER or LAYER[dst] <= LAYER[src]:
                    continue
                edges.setdefault((src, dst), []).append(str(py.relative_to(ROOT)))
    return edges


def test_no_new_eager_upward_imports() -> None:
    """Fail on any eager upward import not in the documented baseline."""
    edges = _eager_upward_edges()
    new = {edge: files for edge, files in edges.items() if edge not in ALLOWED_UPWARD}
    assert not new, "New upward (eager) imports violate the doc-58 layering:\n" + "\n".join(
        f"  L{LAYER[s]} {s} -> L{LAYER[d]} {d}  (e.g. {files[0]})"
        for (s, d), files in sorted(new.items())
    )


def _runtime_imports_between(pkg: str, targets: set[str]) -> list[str]:
    """Module-top (runtime) imports from ``pkg`` into any of ``targets``."""
    offenders: list[str] = []
    for py in (ROOT / pkg).rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        for dst in _module_top_imports(py):
            if dst in targets:
                offenders.append(f"{py.name} -> {dst}")
    return offenders


def test_cache_is_a_leaf() -> None:
    """doc-58: Cache (L4) is a leaf — it must not import KG/Memory/Context/Provider."""
    offenders = _runtime_imports_between(
        "cache", {"graph", "memory", "context", "providers", "retrieval", "indexing"}
    )
    assert not offenders, f"cache (L4 leaf) imports knowledge layers: {offenders}"


def test_kg_and_memory_do_not_import_each_other() -> None:
    """doc-58: KG ↔ Memory are L4 siblings — they meet in L5, never import at runtime."""
    assert not _runtime_imports_between("graph", {"memory"}), "graph imports memory (sibling cycle)"
    assert not _runtime_imports_between("memory", {"graph"}), "memory imports graph (sibling cycle)"


@pytest.mark.parametrize("a,b", [("sdd", "oc_flow"), ("oc_flow", "sdd"), ("sdd", "oc_new")])
def test_workflows_do_not_import_each_other(a: str, b: str) -> None:
    """doc-58: Workflows (L9) never import each other; they share only L1-L8."""
    offenders = _runtime_imports_between(a, {b})
    assert not offenders, f"workflow {a} imports workflow {b}: {offenders}"

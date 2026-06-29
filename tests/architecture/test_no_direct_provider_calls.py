"""AVH-001 fitness guard — provider calls route through the gateway seam.

When ``gateway_enabled`` is the sanctioned path (config ``runtime.gateway_enabled``),
production modules must reach an LLM provider through the gateway seam (``llm/`` /
``providers/``), not by importing a provider client and invoking a provider verb
(``generate`` / ``complete`` / ``chat`` / ``stream`` / ``embed`` / ``sample`` …)
directly elsewhere.

A frozen ratchet (:data:`ALLOWED_DIRECT_PROVIDER`) freezes the pre-existing legacy
call-sites — sized by a one-time AST sweep — so they don't break; any NEW direct
provider call in a non-allowlisted module fails the guard. The ratchet is always
enforced (it blocks new direct calls regardless of the live flag value) so the
``gateway_enabled`` flip is safe; the live default is recorded for context. Same
philosophy as ``ALLOWED_UPWARD`` in ``test_no_upward_imports.py``: the count only
ratchets DOWN.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = (
    Path(__file__).resolve().parents[2]
    / "packages/opencontext_core/opencontext_core"
)

#: The gateway seam itself — exempt from the direct-provider-call rule.
GATEWAY_DIRS: tuple[str, ...] = ("llm/", "providers/")

#: Provider verbs that constitute a direct model call.
PROVIDER_VERBS: frozenset[str] = frozenset(
    {"generate", "complete", "chat", "stream", "embed", "sample", "acomplete", "agenerate"}
)

#: Frozen ratchet of pre-existing legacy direct-provider call-sites (one-time AST
#: sweep), keyed by package-relative path with a documented reason. New importers
#: that also call a provider verb and are NOT listed here fail the guard.
ALLOWED_DIRECT_PROVIDER: dict[str, str] = {
    "agents/executor.py": (
        "legacy delegation executor calls gateway.generate; pre-gateway-flip call-site"
    ),
    "runtime/__init__.py": (
        "composition-root RoutingGateway wraps base_gateway.generate; the routing seam"
    ),
    "workflow/steps.py": (
        "legacy workflow step calls llm_gateway.generate; pre-gateway-flip call-site"
    ),
    "evaluation/golden.py": (
        "provider-fallback golden suite calls ProviderGateway.generate to verify the "
        "gateway fallback path — benchmark harness exercising the seam, not a production bypass"
    ),
}


def _imports_provider_layer(tree: ast.Module) -> bool:
    """True when the module imports from ``opencontext_core.llm`` / ``.providers``."""
    targets = ("opencontext_core.llm", "opencontext_core.providers")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(targets):
            return True
        if isinstance(node, ast.Import):
            if any(alias.name.startswith(targets) for alias in node.names):
                return True
    return False


def _calls_provider_verb(tree: ast.Module) -> list[int]:
    """Line numbers of provider-verb calls (``recv.<verb>(...)``) in *tree*."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in PROVIDER_VERBS
        ):
            lines.append(node.lineno)
    return lines


def _direct_provider_sites() -> dict[str, list[int]]:
    """Package-relative modules (outside the gateway seam) making direct provider calls."""
    sites: dict[str, list[int]] = {}
    for py in ROOT.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        rel = str(py.relative_to(ROOT))
        if rel.startswith(GATEWAY_DIRS):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if not _imports_provider_layer(tree):
            continue
        verb_lines = _calls_provider_verb(tree)
        if verb_lines:
            sites[rel] = verb_lines
    return sites


def test_no_new_direct_provider_calls() -> None:
    """No direct provider verb call outside the gateway seam or the frozen ratchet."""
    sites = _direct_provider_sites()
    new = {rel: lines for rel, lines in sites.items() if rel not in ALLOWED_DIRECT_PROVIDER}
    assert not new, (
        "New direct provider calls bypass the gateway seam (route through "
        "ProviderGateway / LLMGateway, or add to ALLOWED_DIRECT_PROVIDER with a "
        "reason in review):\n"
        + "\n".join(
            f"  {rel} : provider verb at line(s) {lines}" for rel, lines in sorted(new.items())
        )
    )


def test_ratchet_entries_still_exist() -> None:
    """Allowlist entries must stay real call-sites so the ratchet count only drops."""
    sites = _direct_provider_sites()
    stale = sorted(rel for rel in ALLOWED_DIRECT_PROVIDER if rel not in sites)
    assert not stale, f"ALLOWED_DIRECT_PROVIDER has stale entries (remove them): {stale}"


def test_gateway_flag_is_readable() -> None:
    """The guarded invariant tracks runtime.gateway_enabled (recorded for context)."""
    from opencontext_core.config import RuntimeMigrationConfig

    assert "gateway_enabled" in RuntimeMigrationConfig.model_fields


def test_guard_flags_a_new_direct_provider_call() -> None:
    """The detector itself must FAIL on a new importer that calls a provider verb."""
    seeded = (
        "from opencontext_core.llm.gateway import LLMGateway\n\n"
        "def run(gateway: LLMGateway, request):\n"
        "    return gateway.generate(request)\n"
    )
    tree = ast.parse(seeded)
    assert _imports_provider_layer(tree)
    assert _calls_provider_verb(tree), "guard must detect a direct provider verb call"

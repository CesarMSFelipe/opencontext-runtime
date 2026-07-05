"""Public agent docs must not preserve stale MCP/OpenCode claims."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DOCS = [
    ROOT / "README.md",
    ROOT / "docs/integrations/claude-code.md",
    ROOT / "docs/integrations/opencode-kilo-code.md",
    ROOT / "docs/integrations/cursor.md",
    ROOT / "packages/opencontext_core/opencontext_core/configurator/profiles/opencode.md",
]


def _body() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_DOCS)


def test_agent_docs_do_not_hardcode_stale_mcp_counts() -> None:
    body = _body()
    assert "32 MCP tools" not in body
    assert "all 14" not in body


def test_opencode_docs_do_not_claim_uninstalled_slash_commands() -> None:
    body = (
        ROOT / "packages/opencontext_core/opencontext_core/configurator/profiles/opencode.md"
    ).read_text(encoding="utf-8")
    assert "/context`, `/impact`, `/search" not in body


def test_opencode_setup_does_not_keep_dead_json_or_wildcard() -> None:
    body = (ROOT / "packages/opencontext_core/opencontext_core/configurator/service.py").read_text(
        encoding="utf-8"
    )
    assert "mcp__opencontext__*" not in body
    assert "_plan_opencode_profile" not in body

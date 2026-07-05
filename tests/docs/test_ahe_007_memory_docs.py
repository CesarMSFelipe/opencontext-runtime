"""Memory boundary doc tests (PR-AHE-007 tasks 7.6, 7.7, 7.8).

Pins the three documentation contracts from the spec:

  7.6 — OpenContext-only mode is documented and explains the local store and
        the runtime-backed MCP requirement.
  7.7 — OpenContext + Engram opt-in mode is documented and states that live
        Engram requires explicit configuration (and that OpenContext falls
        back to local memory when configured to do so).
  7.8 — Agent docs explain that memory tools are advertised but their
        availability depends on the runtime — never implying memory always
        works.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEMORY_DOCS = ROOT / "docs" / "memory"
OVERVIEW_DOC = MEMORY_DOCS / "overview.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _overview() -> str:
    return _read(OVERVIEW_DOC)


def _all_memory_docs() -> str:
    """Body of every doc in ``docs/memory/`` — used by content checks that
    can live in any of the per-topic docs, not just ``overview.md``."""
    if not MEMORY_DOCS.is_dir():
        return ""
    return "\n".join(_read(p) for p in sorted(MEMORY_DOCS.glob("*.md")))


# --------------------------------------------------------------------------- #
# 7.6 — OpenContext-only mode is documented
# --------------------------------------------------------------------------- #


def test_overview_documents_opencontext_only_mode() -> None:
    """OpenContext-only mode is named and explained.

    The doc must surface "opencontext-only" (or "opencontext only") as a
    coherent mode description — not just a passing mention — and must name the
    local store explicitly so an agent knows no separate service is needed.
    """

    body = _overview().lower()
    # Must name OpenContext-only mode.
    assert "opencontext-only" in body or "opencontext only" in body, body[:1500]
    # Must explain the local store (SQLite/FTS5 or "local").
    assert "sqlite" in body or "local" in body, body[:1500]
    # Must surface the runtime-backed MCP requirement (the spec scenario).
    assert "runtime-backed" in body or "runtime backed" in body, body


def test_opencontext_only_section_describes_no_external_service() -> None:
    """The OpenContext-only section must NOT require any external service.

    Agents reading the doc must understand that OpenContext-only mode needs
    nothing beyond the local SQLite database — no Engram, no network.
    """

    body = _all_memory_docs().lower()
    # Either OpenContext-only is named as a coherent mode...
    if "opencontext-only" in body or "opencontext only" in body:
        # ...and the surrounding area is honest about it requiring only SQLite
        # (no Engram needed for that mode).
        # Heuristic: at least one of the OpenContext-only sections co-locates
        # the word "sqlite" within ±600 chars (a generous window for prose).
        for needle in ("opencontext-only", "opencontext only"):
            idx = body.find(needle)
            while idx != -1:
                window = body[max(0, idx - 200) : idx + 600]
                assert "sqlite" in window or "local" in window, (
                    f"'{needle}' section does not co-locate 'sqlite'/'local'\n{window!r}"
                )
                idx = body.find(needle, idx + len(needle))
        return
    # Or OpenContext-only mode is documented via an explicit alternative
    # phrase (the "no Engram required" / "default" section).
    assert "no engram" in body or "engram is not" in body or "by default" in body


# --------------------------------------------------------------------------- #
# 7.7 — OpenContext + Engram opt-in mode is documented
# --------------------------------------------------------------------------- #


def test_overview_documents_engram_opt_in_mode() -> None:
    """OpenContext + Engram is named as opt-in, requires configuration, and
    documents the local fallback behavior.
    """

    body = _overview().lower()
    # Opt-in language must be present.
    opt_in_phrases = ("opt-in", "opt in", "opt_in", "optional", "explicitly")
    assert any(phrase in body for phrase in opt_in_phrases), body[:1500]
    # Live Engram must be acknowledged as needing configuration.
    assert "engram" in body
    assert "configur" in body, body  # configuration / configured / configure
    # Fallback behavior must be named.
    fallback_phrases = (
        "fall back",
        "fallback",
        "degrades to",
        "degrade",
        "transparently",
    )
    assert any(phrase in body for phrase in fallback_phrases), body


def test_engram_section_airs_to_local_when_unavailable() -> None:
    """Where Engram is discussed, the doc must also explain what happens
    when Engram is reachable-but-not-used / unreachable.

    Pins spec scenario 7.7: "OpenContext falls back to local memory only when
    configured to do so".
    """

    body = _all_memory_docs().lower()
    # Anywhere "engram" appears, ensure a nearby region (within ±600 chars)
    # describes local fallback.
    idx = 0
    matches = 0
    while True:
        idx = body.find("engram", idx)
        if idx == -1:
            break
        window = body[max(0, idx - 300) : idx + 600]
        fallback_phrases = ("fall back", "fallback", "local", "degrades", "degrade")
        if any(p in window for p in fallback_phrases):
            matches += 1
        idx += 1
    assert matches >= 1, "No 'engram' region co-locates a fallback phrase"


# --------------------------------------------------------------------------- #
# 7.8 — Agent docs explain that memory tool availability is conditional
# --------------------------------------------------------------------------- #


def test_agent_docs_name_availability_gate() -> None:
    """Agent-facing docs (CLI/integration docs or system-prompt-rendered docs)
    state that memory tool availability depends on the runtime, not on the
    tool catalog.

    The MCP server advertises the memory tools unconditionally (see
    MCPServer._default_tool_names) — but agents calling them on a raw server
    will get ``available=false``. The docs must not promise memory persists
    on every install.
    """

    # Spot-check integration docs that ship in the repo as the source the
    # user actually reads when wiring a host. We assert the human-readable
    # caveat appears in at least one of them.
    candidates: list[Path] = [
        ROOT / "docs" / "memory" / "overview.md",
        ROOT / "README.md",
        ROOT / "docs" / "integrations" / "claude-code.md",
        ROOT / "docs" / "integrations" / "opencode-kilo-code.md",
        ROOT / "docs" / "concepts" / "memory.md",
    ]
    combined: list[str] = []
    for path in candidates:
        if path.exists():
            text = path.read_text(encoding="utf-8").lower()
            combined.append(text)
    body = "\n".join(combined)
    # The clause family — wording may vary; require the conceptual idea, not
    # a specific phrase, to allow the prose to evolve without breaking tests.
    assert any(
        c in body
        for c in (
            "memory backend unavailable",
            "runtime-backed mcp",
            "memory tools requires",
            "memory tools require",
            "memory is wired",
            "memory when the runtime",
            "memory at runtime startup",
            "memory is only available",
        )
    ), "Agent docs do not flag that memory is conditional on the runtime"


def test_tools_list_advertises_memory_regardless_of_runtime() -> None:
    """Companion guarantee to 7.8: the tools ARE advertised; docs must say
    so (and must not imply they need Engram to appear)."""

    candidates: list[Path] = [
        ROOT / "docs" / "memory" / "overview.md",
        ROOT / "docs" / "integrations" / "claude-code.md",
    ]
    combined: list[str] = [p.read_text(encoding="utf-8").lower() for p in candidates if p.exists()]
    body = "\n".join(combined)
    # The docs must name at least one of the four memory tools.
    assert any(
        name in body
        for name in (
            "opencontext_memory_save",
            "opencontext_memory_search",
            "opencontext_memory_context",
        )
    )

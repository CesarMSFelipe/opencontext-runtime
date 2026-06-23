"""Regression guard: every OpenContext-shipped entry point carries an
``oc-`` / ``opencontext_`` prefix.

This locks the naming invariant restored by workstream D of
``oc-memory-parity-and-polish`` (the ``sdd-*`` -> ``oc-*`` collision fix). It
MUST fail if a future template/install regression reintroduces a bare ``sdd-*``
(or any otherwise-unprefixed) OC entry point — proven below by a planted
``sdd-foo`` case (Scenario D3-1b).

The inventory is **derived from three live sources** (design N5), never a
hand-declared list (a declared list silently rots when a new surface is added):

1. **Skill names**  = directory names under ``skills/templates/`` (the same dir
   the registry scanner reads). Allowed: ``oc-`` prefix, or the exact
   allowlisted agent-template dir ``opencontext-agent``.
2. **MCP tool names** = ``MCPServer(...)._default_tool_names()`` (constructed
   with a tmp db + ``runtime=None``). This list INCLUDES the four
   ``opencontext_memory_*`` tools once workstream A lands. Allowed: ``opencontext_``.
3. **Persona ids**  = ``[p.id for p in personas.PERSONAS]``. Allowed: ``oc-``.

EXPLICIT EXCLUSION (D3-REQ-1's "MUST NOT flag third-party"): ``agents/registry.py``
``AgentCapabilities`` ids (``opencode``, ``cursor``, ``claude-code``, ...) are the
names of the *third-party CLIs OpenContext integrates with*, which OC does not own.
They are deliberately NOT asserted here. Do not "fix" this file by adding them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from opencontext_core import personas
from opencontext_core.mcp_stdio import MCPServer

# The agent-template dir is the one shipped skill whose name is not ``oc-``-prefixed
# but is still a legitimate OpenContext entry point.
_ALLOWLISTED_SKILL_NAMES = {"opencontext-agent"}

_TEMPLATES_DIR = Path(personas.__file__).resolve().parent / "skills" / "templates"


def _shipped_skill_names() -> list[str]:
    """Skill names = template *directory* names under ``skills/templates/``.

    Mirrors the source-of-truth the registry scanner reads. Files (e.g.
    ``spec_template.md``) are not skills and are excluded.
    """
    return sorted(p.name for p in _TEMPLATES_DIR.iterdir() if p.is_dir())


def _shipped_mcp_tool_names(tmp_path: Path) -> list[str]:
    """MCP tool names from the live default allowlist (no runtime needed)."""
    server = MCPServer(db_path=tmp_path / "naming-guard.db", runtime=None)
    return list(server._default_tool_names())


def _shipped_persona_ids() -> list[str]:
    return [p.id for p in personas.PERSONAS]


def _is_oc_skill_name(name: str) -> bool:
    return name.startswith("oc-") or name in _ALLOWLISTED_SKILL_NAMES


def test_shipped_skill_dirs_are_oc_prefixed() -> None:
    """Every template skill dir is ``oc-*`` or the allowlisted agent template."""
    names = _shipped_skill_names()
    assert names, "no skill template directories were discovered"
    offenders = [n for n in names if not _is_oc_skill_name(n)]
    assert not offenders, (
        f"un-prefixed OC skill template dir(s): {offenders} "
        f"(expected 'oc-' prefix or allowlisted {_ALLOWLISTED_SKILL_NAMES})"
    )


def test_no_stale_sdd_skill_templates() -> None:
    """The migrated-away ``sdd-*`` template dirs must not reappear in source."""
    stale = [n for n in _shipped_skill_names() if n.startswith("sdd-")]
    assert not stale, f"stale sdd-* skill template dir(s) reintroduced: {stale}"


def test_shipped_mcp_tool_names_are_opencontext_prefixed(tmp_path: Path) -> None:
    """Every default MCP tool name carries the ``opencontext_`` prefix."""
    names = _shipped_mcp_tool_names(tmp_path)
    assert names, "MCPServer advertised no default tool names"
    offenders = [n for n in names if not n.startswith("opencontext_")]
    assert not offenders, f"un-prefixed MCP tool name(s): {offenders}"


def test_shipped_persona_ids_are_oc_prefixed() -> None:
    """Every shipped persona id carries the ``oc-`` prefix."""
    ids = _shipped_persona_ids()
    assert ids, "personas.PERSONAS is empty"
    offenders = [pid for pid in ids if not pid.startswith("oc-")]
    assert not offenders, f"un-prefixed persona id(s): {offenders}"


# --- Scenario D3-1b: the guard MUST catch a reintroduced bare entry point. ---
# Plant fake entry-point names directly against the same predicates the live
# assertions use; each MUST be flagged. This proves the guard fails closed if a
# future regression reintroduces a bare ``sdd-*`` (or any non-oc-) name, without
# mutating the real on-disk template dir.

_PLANTED_BARE_NAMES = ["sdd-foo", "sdd-new", "acme-apply", "foo-run"]


@pytest.mark.parametrize("planted", _PLANTED_BARE_NAMES)
def test_guard_flags_planted_bare_skill_name(planted: str) -> None:
    """A planted un-prefixed skill name is rejected by the skill predicate."""
    assert not _is_oc_skill_name(planted), (
        f"guard FAILED to flag planted bare skill name {planted!r}"
    )


@pytest.mark.parametrize("planted", _PLANTED_BARE_NAMES)
def test_guard_flags_planted_bare_mcp_tool_name(planted: str) -> None:
    """A planted un-prefixed MCP tool name fails the ``opencontext_`` check."""
    assert not planted.startswith("opencontext_"), (
        f"guard FAILED to flag planted bare MCP tool name {planted!r}"
    )


@pytest.mark.parametrize("planted", _PLANTED_BARE_NAMES)
def test_guard_flags_planted_bare_persona_id(planted: str) -> None:
    """A planted un-prefixed persona id fails the ``oc-`` check."""
    assert not planted.startswith("oc-"), (
        f"guard FAILED to flag planted bare persona id {planted!r}"
    )

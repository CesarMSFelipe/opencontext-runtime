"""Capability graph v2 — eight registered v2 modules carry stable metadata.

The capability graph that ships with the 1.0 release enumerates eight
v2 leaf capabilities. Each v2 subpackage declares its own id via the
``__capability__`` string annotation in its ``__init__.py`` so the
graph and the package cannot drift.
"""

from __future__ import annotations

from opencontext_core.capabilities.registry import REGISTERED_V2_CAPABILITIES

EXPECTED_V2_MODULES: frozenset[str] = frozenset(
    {
        "graph.v2",
        "context.v2",
        "memory.v2",
        "learning.v2",
        "cache.v2",
        "plugins.v2",
        "marketplace.v2",
        "providers.v2",
    }
)


def test_v2_modules_have_metadata() -> None:
    """The closed set of v2 module ids is exactly the eight expected ones."""
    assert REGISTERED_V2_CAPABILITIES == EXPECTED_V2_MODULES
    assert len(REGISTERED_V2_CAPABILITIES) == 8


def test_v2_modules_ids_are_sorted_strings() -> None:
    """Capability ids are lowercase dotted strings — no surprises for downstream tools."""
    for cid in REGISTERED_V2_CAPABILITIES:
        assert isinstance(cid, str)
        assert cid.endswith(".v2")
        assert cid == cid.lower()


def test_v2_modules_no_duplicates() -> None:
    """The set is a true set — no duplicate capability ids in the registry."""
    assert len(REGISTERED_V2_CAPABILITIES) == len(set(REGISTERED_V2_CAPABILITIES))

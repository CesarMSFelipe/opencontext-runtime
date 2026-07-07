"""Canonical memory type taxonomy (MEMORY_CONTRACT `## Types`).

The contract pins eight canonical observation types. Plan-level vocabulary
(`project_rule`, `learned_pattern`, `error_resolution`) normalizes onto the
canonical set at save time; every other value passes through verbatim so the
historical free-form types (`manual`, `bugfix`, `discovery`, `summary`, ...)
keep working — validation is additive, never a rejection.

Known deviation (recorded): the closure plan lists `summary` as a type while
the contract's canonical set does not include it. `summary` therefore remains
a free-form pass-through type (used by compaction summaries) until the plan
and the contract agree on one vocabulary.
"""

from __future__ import annotations

#: MEMORY_CONTRACT `## Types` — the canonical observation type set.
CANONICAL_MEMORY_TYPES: frozenset[str] = frozenset(
    {
        "fact",
        "decision",
        "preference",
        "constraint",
        "pattern",
        "failure",
        "solution",
        "project_context",
    }
)

#: Plan-level names → their canonical contract equivalents.
MEMORY_TYPE_ALIASES: dict[str, str] = {
    "project_rule": "constraint",
    "learned_pattern": "pattern",
    "error_resolution": "solution",
}


def normalize_memory_type(value: str) -> str:
    """Map a save-time type onto the canonical taxonomy (additive).

    Canonical types and unknown/legacy free-form types return unchanged;
    documented aliases return their canonical equivalent.
    """
    cleaned = str(value or "").strip()
    return MEMORY_TYPE_ALIASES.get(cleaned, cleaned)


__all__ = ["CANONICAL_MEMORY_TYPES", "MEMORY_TYPE_ALIASES", "normalize_memory_type"]

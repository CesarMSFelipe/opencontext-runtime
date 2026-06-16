"""Partial-path incremental name resolution for the knowledge graph.

A bare name (``save``) is often ambiguous — many files define one. A *reference*
usually carries scope: ``models.save``, ``AuthService.login``,
``pkg.mod.Class.method``. This resolver walks that dotted path incrementally:
the last segment is the symbol, the preceding segments are scope hints, and the
candidate set is narrowed one hint at a time (closest scope first). If the path
never narrows to a single symbol it returns ``None`` rather than guessing — the
same fail-closed stance the cross-file edge resolver takes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolRef:
    """The minimum a node needs to expose to be resolvable by path."""

    id: str
    name: str
    container: str | None
    file_path: str


def _file_has_segment(file_path: str, hint: str) -> bool:
    """True if ``hint`` names a directory segment or the file stem of the path."""
    parts = file_path.replace("\\", "/").split("/")
    if hint in parts:
        return True
    stem = parts[-1].rsplit(".", 1)[0] if parts else ""
    return stem == hint


def _matches_hint(ref: SymbolRef, hint: str) -> bool:
    if ref.container and hint in ref.container.split("."):
        return True
    return _file_has_segment(ref.file_path, hint)


def resolve_partial_path(path: str, refs: list[SymbolRef]) -> str | None:
    """Resolve a dotted reference to a unique node id, or None if unresolved.

    Args:
        path: A dotted reference, e.g. ``"AuthService.login"`` or ``"save"``.
        refs: Candidate symbols (typically every node, or every node for one name).

    Returns:
        The id of the single matching symbol, or ``None`` when there is no
        candidate or the path stays ambiguous.
    """
    segments = [s for s in path.split(".") if s]
    if not segments:
        return None
    leaf, hints = segments[-1], segments[:-1]

    candidates = [r for r in refs if r.name == leaf]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0].id

    # Walk the scope hints from the closest (rightmost) outward, narrowing the
    # candidate set each time it helps. A hint that matches nothing is skipped
    # (the reference may name an alias or a re-export we did not index).
    for hint in reversed(hints):
        narrowed = [r for r in candidates if _matches_hint(r, hint)]
        if len(narrowed) == 1:
            return narrowed[0].id
        if narrowed:
            candidates = narrowed

    return None  # still ambiguous — do not bind arbitrarily

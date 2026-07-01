"""organization.graph — REQ-org-graph-001..004 owner hooks.

1.0 ships the parser + resolver + escalation hook.  The full org graph
(reporting lines, teams, squads) is 1.x per the spec's Out-of-Scope list.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


OwnerSource = Literal["codeowners", "git", "manual", "unknown"]


class OwnerRef(BaseModel):
    """REQ-org-graph-001 — Pydantic model so JSON round-trips cleanly."""

    source: OwnerSource
    username: str
    email: str | None = None
    last_verified: datetime = Field(default_factory=lambda: datetime.now(UTC))


@dataclass
class OrgNode:
    """One node in the org graph (team, repo, bot, person)."""

    id: str
    kind: str
    name: str = ""


@dataclass
class OrgEdge:
    """Directed edge between two ``OrgNode`` ids."""

    src: str
    dst: str
    relation: str = "owns"


@dataclass
class TeamOwnership:
    """Mapping from a team to a scope (e.g. ``repo:foo``)."""

    team_id: str
    scope: str


@dataclass
class CODEOWNERSFile:
    """REQ-org-graph-002 — parsed CODEOWNERS rules.

    Each rule is a ``(pattern, owners)`` pair.  Patterns are gitignore-style
    paths with a leading ``/`` rooted at the repo root.
    """

    rules: list[tuple[str, list[str]]] = field(default_factory=list)

    @classmethod
    def parse(cls, text: str) -> CODEOWNERSFile:
        rules: list[tuple[str, list[str]]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pattern = parts[0]
            # Keep only @-prefixed owners; the literal "OWNERS" keyword (and
            # similar) is GitHub's optional "team slug" prefix-less form, which
            # we don't model in 1.0.
            owners = [o for o in parts[1:] if o.startswith("@") or "@" in o]
            if not owners:
                owners = parts[1:]
            rules.append((pattern, owners))
        return cls(rules=rules)

    def match(self, path: str) -> list[str] | None:
        """Return the FIRST matching owners list, or ``None``."""
        for pattern, owners in self.rules:
            if _match_codeowners(pattern, path):
                return owners
        return None


def _match_codeowners(pattern: str, path: str) -> bool:
    """Match a single CODEOWNERS pattern against a repo path.

    Supports:
    - leading ``/`` → anchored to repo root
    - trailing ``/**`` → directory + descendants
    - ``*`` wildcards (segment-level)
    - bare names → any depth match
    """
    if pattern.startswith("/"):
        anchored = pattern[1:]
        return _glob_match(anchored, path)
    # No leading slash → match at any depth
    return _glob_match(pattern, path) or _glob_match(pattern, path.lstrip("/"))


def _glob_match(pattern: str, path: str) -> bool:
    """Match a single CODEOWNERS pattern segment (no leading slash).

    Supports:
    - ``**``  → zero or more path segments
    - ``*``   → exactly one path segment
    - leading segment is fnmatch-compared
    """
    pat = pattern.lstrip("/")
    p = path.lstrip("/")
    if "**" in pat:
        head, _, tail = pat.partition("**")
        if head and head.rstrip("/"):
            head_clean = head.rstrip("/")
            # Match the head against the head of p, segment by segment
            if not _head_matches(head_clean, p):
                return False
        if tail.startswith("/"):
            tail = tail[1:]
        if not tail:
            return True
        # Tail is a suffix pattern — match at any segment boundary.
        return _tail_matches(tail, p)
    return fnmatch.fnmatch(p, pat)


def _head_matches(head: str, p: str) -> bool:
    """Match the head segment-by-segment (each segment is fnmatch)."""
    head_segs = [s for s in head.split("/") if s]
    p_segs = p.split("/")
    if len(p_segs) < len(head_segs):
        return False
    for hs, ps in zip(head_segs, p_segs[: len(head_segs)], strict=False):
        if not fnmatch.fnmatchcase(ps, hs):
            return False
    return True


def _tail_matches(tail: str, p: str) -> bool:
    """Match the tail (which may include ``*``) against any suffix of ``p``."""
    # Walk all segment boundaries
    for i in range(len(p)):
        suffix = p[i:]
        if fnmatch.fnmatchcase(suffix, tail):
            return True
    return fnmatch.fnmatchcase(p, f"*{tail}")


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


@dataclass
class EscalationNotice:
    """REQ-org-graph-004 — surfaced in the Decision Log; no auto-page."""

    path: str
    reason: str
    dimension: str
    ts: datetime = field(default_factory=lambda: datetime.now(UTC))


class OwnerResolver:
    """REQ-org-graph-002..003 — CODEOWNERS > git > unknown.

    The git-blame leg is a soft signal (recent commit ≠ owner).  For 1.0 the
    resolver only consults CODEOWNERS — the rest of the priority order is
    represented in the API surface so the 1.x git-blame wiring slots in
    without callers changing.
    """

    def __init__(
        self,
        codeowners: CODEOWNERSFile | None = None,
        *,
        git_authors: dict[str, str] | None = None,
    ) -> None:
        self._codeowners = codeowners
        self._git_authors = git_authors or {}

    def resolve(self, path: str) -> OwnerRef:
        if self._codeowners is not None:
            owners = self._codeowners.match(path)
            if owners:
                return OwnerRef(
                    source="codeowners",
                    username=owners[0],
                )
        author = self._git_authors.get(path)
        if author:
            return OwnerRef(source="git", username=author)
        return OwnerRef(source="unknown", username="")

    def escalate(
        self,
        path: str,
        dimension: str,
        kind: str = "mutation",
    ) -> tuple[OwnerRef, EscalationNotice | None]:
        ref = self.resolve(path)
        if ref.source == "unknown" and kind in {"mutation", "policy-violation"}:
            return ref, EscalationNotice(
                path=path,
                reason=f"unknown owner for {kind} on {path}",
                dimension=dimension,
            )
        return ref, None


# ---------------------------------------------------------------------------
# Org graph
# ---------------------------------------------------------------------------


@dataclass
class OrgGraph:
    """In-memory org graph (1.0 hooks; full graph is 1.x per spec)."""

    nodes: dict[str, OrgNode] = field(default_factory=dict)
    edges: list[OrgEdge] = field(default_factory=list)
    ownership: list[TeamOwnership] = field(default_factory=list)

    def find_owner(self, scope: str) -> OrgNode | None:
        """Return the owning team node for a scope, or ``None``.

        Priority: explicit ``ownership`` entries first, then the node whose
        ``id`` matches ``scope`` (handy for unit tests + 1.x graph walks).
        """
        for entry in self.ownership:
            if entry.scope == scope:
                node = self.nodes.get(entry.team_id)
                if node is not None:
                    return node
        if scope in self.nodes:
            return self.nodes[scope]
        for edge in self.edges:
            if edge.relation != "owns":
                continue
            if edge.dst == scope or scope == edge.dst:
                return self.nodes.get(edge.src)
        return None


def build_org_graph(
    *,
    nodes: Iterable[OrgNode],
    edges: Iterable[OrgEdge],
    ownership: Iterable[TeamOwnership] = (),
) -> OrgGraph:
    graph = OrgGraph(
        nodes={n.id: n for n in nodes},
        edges=list(edges),
        ownership=list(ownership),
    )
    return graph


__all__ = [
    "CODEOWNERSFile",
    "EscalationNotice",
    "OrgEdge",
    "OrgGraph",
    "OrgNode",
    "OwnerRef",
    "OwnerResolver",
    "TeamOwnership",
    "build_org_graph",
]

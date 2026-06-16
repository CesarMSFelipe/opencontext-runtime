"""Structured, decodable symbol identity for knowledge-graph nodes.

An opaque hash uniquely names a symbol but tells you nothing about it. A
*structured* symbol string carries the language, package, file, enclosing types,
and the symbol's role, so two tools — and two repositories — can agree on what a
symbol IS, and a reader can decode it without the database.

Format (space-separated header, then a run of descriptors):

    <scheme> <manager> <package> <version> <descriptors>

Descriptor suffixes encode the role of each path segment:

    seg/      namespace  (package / module / file segment)
    Name#     type       (class / struct / interface / enum / trait)
    name().   method     (function / method)
    name.     term       (variable / constant / field / attribute)

Identifiers containing a suffix character, a space, or a backtick are wrapped in
backticks with internal backticks doubled, so the string always round-trips.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SCHEME = "opencontext"
_LOCAL_VERSION = "."
_SAFE_IDENT = re.compile(r"^[A-Za-z0-9_$+-]+$")

# Descriptor roles -> the suffix that encodes them.
_NAMESPACE = "/"
_TYPE = "#"
_METHOD = "()."
_TERM = "."

# Map a parser ``kind`` onto a descriptor role suffix for the leaf symbol.
_KIND_SUFFIX: dict[str, str] = {
    "class": _TYPE,
    "struct": _TYPE,
    "interface": _TYPE,
    "enum": _TYPE,
    "trait": _TYPE,
    "type": _TYPE,
    "function": _METHOD,
    "method": _METHOD,
    "constructor": _METHOD,
    "module": _NAMESPACE,
    "namespace": _NAMESPACE,
    "package": _NAMESPACE,
    "variable": _TERM,
    "constant": _TERM,
    "field": _TERM,
    "attribute": _TERM,
    "property": _TERM,
}


@dataclass(frozen=True)
class Descriptor:
    """One segment of a symbol path: its name and its role suffix."""

    name: str
    suffix: str


def _escape(name: str) -> str:
    if _SAFE_IDENT.match(name):
        return name
    return "`" + name.replace("`", "``") + "`"


def _encode_descriptor(d: Descriptor) -> str:
    return _escape(d.name) + d.suffix


def format_symbol(
    *,
    language: str,
    file_path: str,
    name: str,
    kind: str,
    container: str | None = None,
    package: str = ".",
) -> str:
    """Build a structured symbol string for a node from its stored fields.

    The file path becomes namespace descriptors, the (possibly dotted) container
    becomes type descriptors, and the leaf name takes the suffix for its kind.
    """
    manager = language or "unknown"
    descriptors: list[Descriptor] = []
    for seg in file_path.split("/"):
        if seg:
            descriptors.append(Descriptor(seg, _NAMESPACE))
    if container:
        for seg in container.split("."):
            if seg:
                descriptors.append(Descriptor(seg, _TYPE))
    descriptors.append(Descriptor(name, _KIND_SUFFIX.get(kind, _TERM)))

    body = "".join(_encode_descriptor(d) for d in descriptors)
    return f"{SCHEME} {manager} {package or '.'} {_LOCAL_VERSION} {body}"


def _split_descriptors(body: str) -> list[Descriptor]:
    """Tokenize the descriptor run, honoring backtick-escaped identifiers."""
    out: list[Descriptor] = []
    i = 0
    n = len(body)
    while i < n:
        # Read one (possibly backtick-escaped) identifier.
        if body[i] == "`":
            j = i + 1
            chars: list[str] = []
            while j < n:
                if body[j] == "`":
                    if j + 1 < n and body[j + 1] == "`":
                        chars.append("`")
                        j += 2
                        continue
                    break
                chars.append(body[j])
                j += 1
            name = "".join(chars)
            i = j + 1  # skip closing backtick
        else:
            j = i
            while j < n and body[j] not in "/#.(":
                j += 1
            name = body[i:j]
            i = j
        # Read the suffix that follows the identifier.
        if body.startswith("().", i):
            suffix = _METHOD
            i += 3
        elif i < n and body[i] == "#":
            suffix = _TYPE
            i += 1
        elif i < n and body[i] == "/":
            suffix = _NAMESPACE
            i += 1
        elif i < n and body[i] == ".":
            suffix = _TERM
            i += 1
        else:
            suffix = _TERM
        out.append(Descriptor(name, suffix))
    return out


@dataclass(frozen=True)
class ParsedSymbol:
    """A decoded symbol: header fields plus the ordered descriptor path."""

    scheme: str
    manager: str
    package: str
    version: str
    descriptors: list[Descriptor]

    @property
    def leaf(self) -> str:
        """The bare name of the final descriptor (the symbol itself)."""
        return self.descriptors[-1].name if self.descriptors else ""


def parse_symbol(symbol: str) -> ParsedSymbol:
    """Decode a structured symbol string back into its parts (round-trips)."""
    parts = symbol.split(" ", 4)
    if len(parts) < 5:
        raise ValueError(f"not a structured symbol: {symbol!r}")
    scheme, manager, package, version, body = parts
    return ParsedSymbol(scheme, manager, package, version, _split_descriptors(body))

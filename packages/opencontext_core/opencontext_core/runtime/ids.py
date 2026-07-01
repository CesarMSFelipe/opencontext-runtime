"""Global ID factory (doc 59 — Global IDs).

One ID scheme, prefixed and time-ordered (ULID-style) for event-like entities.
No ``Date.now()``/``random`` scattered through the codebase — ids are minted
here so the prefix scheme stays consistent (``dec_<ulid>``, ``rcpt_<ulid>``,
``sess_<ulid>``, ``run_<ulid>``).

Stdlib only: a 48-bit millisecond timestamp followed by 80 bits of randomness,
encoded with Crockford base32 into a sortable 26-character string. This gives
lexicographic = chronological ordering without a third-party ``ulid`` dependency.
"""

from __future__ import annotations

import hashlib
import os
import time

# Crockford base32 alphabet (excludes I, L, O, U to avoid ambiguity).
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _ulid() -> str:
    """Return a 26-character, time-ordered, Crockford-base32 ULID string."""
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    randomness = int.from_bytes(os.urandom(10), "big")
    value = (timestamp_ms << 80) | randomness
    chars = [""] * 26
    for i in range(25, -1, -1):
        value, remainder = divmod(value, 32)
        chars[i] = _CROCKFORD[remainder]
    return "".join(chars)


def new_id(prefix: str) -> str:
    """Mint a prefixed, time-ordered id (``<prefix>_<ulid>``)."""
    return f"{prefix}_{_ulid()}"


def new_decision_id() -> str:
    """Mint a ``dec_<ulid>`` decision id (doc 59)."""
    return new_id("dec")


def new_receipt_id() -> str:
    """Mint a ``rcpt_<ulid>`` receipt id (doc 59)."""
    return new_id("rcpt")


def new_session_id() -> str:
    """Mint a ``sess_<ulid>`` session id (doc 59)."""
    return new_id("sess")


def new_run_id() -> str:
    """Mint a ``run_<ulid>`` run id (doc 59)."""
    return new_id("run")


def new_kg_id(content_hash: bytes | str) -> str:
    """Derive a stable KG identifier from content (PR-008.a).

    Uses SHA-256 truncated to 16 hex chars so node/edge IDs are
    deterministic across re-index runs.
    """
    if isinstance(content_hash, str):
        content_hash = content_hash.encode("utf-8")
    return hashlib.sha256(content_hash).hexdigest()[:16]

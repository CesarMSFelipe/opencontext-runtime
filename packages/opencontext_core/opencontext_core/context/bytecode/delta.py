"""Cross-turn AICX delta: send only what changed since the previous bytecode.

Within a session the heavy part of a bytecode — the dictionary of full evidence
values — overlaps heavily turn to turn. A delta re-sends the (cheap) key list
but only the values that are new or changed, so the previous turn's dictionary
is reused instead of retransmitted.

The delta carries the full key set so ``apply_delta`` reconstructs the *exact*
new dictionary (not a superset) — the checksum covers the dictionary, so an exact
rebuild keeps the checksum valid. Applying against the wrong base is refused.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from opencontext_core.context.bytecode.models import (
    VERSION,
    BytecodeInstruction,
    ContextBytecode,
)


class DeltaBaseMismatchError(ValueError):
    """The delta's base does not match the bytecode it is applied to."""


class BytecodeDelta(BaseModel):
    """Patch from a base bytecode to a new one, omitting unchanged values."""

    version: str = VERSION
    request_id: str
    base_request_id: str
    base_checksum: str
    # Full key set of the new bytecode (cheap: keys are short hashes). Lets
    # apply_delta rebuild the exact dictionary so the checksum stays valid.
    dict_keys: list[str] = Field(default_factory=list)
    # Heavy values, only for keys that are new or changed vs the base.
    added_dictionary: dict[str, str] = Field(default_factory=dict)
    instructions: list[BytecodeInstruction] = Field(default_factory=list)
    checksum: str


def diff_bytecode(prev: ContextBytecode, new: ContextBytecode) -> BytecodeDelta:
    """Build a delta that turns ``prev`` into ``new``, omitting unchanged values."""
    added = {k: v for k, v in new.dictionary.items() if prev.dictionary.get(k) != v}
    return BytecodeDelta(
        request_id=new.request_id,
        base_request_id=prev.request_id,
        base_checksum=prev.checksum,
        dict_keys=list(new.dictionary),
        added_dictionary=added,
        instructions=new.instructions,
        checksum=new.checksum,
    )


def apply_delta(prev: ContextBytecode, delta: BytecodeDelta) -> ContextBytecode:
    """Reconstruct the new bytecode from a base and a delta.

    Raises :class:`DeltaBaseMismatchError` if the delta was built against a
    different base (checksum mismatch) or references a value absent from both the
    base and the delta — in either case the caller should fall back to the full
    bytecode.
    """
    if prev.checksum != delta.base_checksum:
        raise DeltaBaseMismatchError(
            f"delta base {delta.base_checksum} != bytecode {prev.checksum}"
        )
    merged = {**prev.dictionary, **delta.added_dictionary}
    try:
        dictionary = {key: merged[key] for key in delta.dict_keys}
    except KeyError as exc:
        raise DeltaBaseMismatchError(f"missing dictionary entry {exc}") from exc
    return ContextBytecode(
        version=delta.version,
        request_id=delta.request_id,
        dictionary=dictionary,
        instructions=delta.instructions,
        checksum=delta.checksum,
    )


def delta_savings_pct(prev: ContextBytecode, new: ContextBytecode) -> float:
    """Percent of dictionary-value bytes the delta avoids re-sending (0-100).

    Measures the real win: the share of the new dictionary's value bytes that are
    unchanged from the base and therefore omitted from the delta.
    """
    total = sum(len(v) for v in new.dictionary.values())
    if total <= 0:
        return 0.0
    delta = diff_bytecode(prev, new)
    resent = sum(len(v) for v in delta.added_dictionary.values())
    return round(max(0.0, (1 - resent / total)) * 100, 1)

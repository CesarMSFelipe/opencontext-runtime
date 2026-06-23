"""Surgical-explore coverage must measure per-required-symbol presence (whole-word),
not the old any-vs-none binary — these pin the two bugs the adversarial review found:
the glob-asterisk membership mismatch and spurious substring matches."""

from __future__ import annotations

from opencontext_core.harness.phases import _surgical_coverage


class _Item:
    def __init__(self, content: str = "", source: str = "") -> None:
        self.content = content
        self.source = source


class _Pack:
    def __init__(self, items: list) -> None:
        self.included = items


def test_full_coverage_when_required_symbol_present() -> None:
    pack = _Pack([_Item(content="def slugify(value):\n    return value", source="text.py")])
    assert _surgical_coverage(pack, ["slugify"]) == 1.0


def test_zero_coverage_when_required_symbol_absent() -> None:
    pack = _Pack([_Item(content="def unrelated():\n    pass", source="x.py")])
    assert _surgical_coverage(pack, ["slugify"]) == 0.0


def test_partial_coverage_fraction() -> None:
    pack = _Pack([_Item(content="def slugify(): ...", source="text.py")])
    assert _surgical_coverage(pack, ["slugify", "truncate"]) == 0.5


def test_whole_word_no_spurious_substring_match() -> None:
    # "id" must NOT match inside "width" — substring matching inflated coverage before.
    pack = _Pack([_Item(content="width = compute_width()", source="x.py")])
    assert _surgical_coverage(pack, ["id"]) == 0.0


def test_binary_fallback_when_no_existing_required() -> None:
    # No required term is a real symbol → fall back to any-vs-none.
    assert _surgical_coverage(_Pack([_Item(content="anything")]), []) == 1.0
    assert _surgical_coverage(_Pack([]), []) == 0.0

"""Redaction pipeline acceptance (REQ-data-gov-002, PR-R2-B).

Contract:
- ``RedactionRule(name, pattern)`` matches sensitive values via a named regex.
- ``RedactionPipeline([rules])`` applies rules in order; matches are replaced
  with ``<REDACTED:<sha256-16hex>>``.
- The redaction tag is **deterministic** (same secret → same tag) so audit
  records can dedupe without ever seeing the original.
- ``apply_redaction(text, rules)`` is the standalone convenience form; the
  pipeline's ``apply(text)`` returns the same shape via :class:`RedactionResult`.
- The original secret **never** appears in the redacted output.
"""
from __future__ import annotations

import re

import pytest

from opencontext_core.governance.redaction import (
    RedactionPipeline,
    RedactionResult,
    RedactionRule,
    apply_redaction,
)

_REDACTED_PREFIX = "<REDACTED:"
_REDACTED_SUFFIX = ">"


def _is_redacted_token(s: str) -> bool:
    """True iff *s* is a ``<REDACTED:16hex>`` token."""
    if not (s.startswith(_REDACTED_PREFIX) and s.endswith(_REDACTED_SUFFIX)):
        return False
    inner = s[len(_REDACTED_PREFIX) : -len(_REDACTED_SUFFIX)]
    return len(inner) == 16 and all(c in "0123456789abcdef" for c in inner)


_API_KEY_RULE = RedactionRule(
    name="api_key",
    pattern=re.compile(r"sk-[A-Za-z0-9]{16,}"),
)
_EMAIL_RULE = RedactionRule(
    name="email",
    pattern=re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)


class TestRedactionRuleBasics:
    def test_rule_replaces_secret_with_deterministic_tag(self) -> None:
        text = "Hello API_KEY=sk-abcdef1234567890 world"
        out = _API_KEY_RULE.apply(text)
        assert "sk-abcdef1234567890" not in out
        assert _is_redacted_token(_extract_replacement(text, out))

    def test_same_secret_same_tag(self) -> None:
        a = _API_KEY_RULE.apply("token=sk-abcdef1234567890")
        b = _API_KEY_RULE.apply("again sk-abcdef1234567890 end")
        assert _extract_replacement("sk-abcdef1234567890", a) == _extract_replacement(
            "sk-abcdef1234567890", b
        )

    def test_no_match_returns_text_unchanged(self) -> None:
        assert _API_KEY_RULE.apply("nothing sensitive here") == "nothing sensitive here"


class TestRedactionPipeline:
    def test_pipeline_applies_first_matching_rule(self) -> None:
        pipe = RedactionPipeline([_API_KEY_RULE, _EMAIL_RULE])
        result = pipe.apply("contact a@b.com via key sk-abcdef1234567890")
        assert "a@b.com" not in result.text
        assert "sk-abcdef1234567890" not in result.text
        assert result.text.count(_REDACTED_PREFIX) == 2

    def test_pipeline_returns_result_with_counts(self) -> None:
        # Two api_key secrets (each >= 16 chars after the sk- prefix).
        pipe = RedactionPipeline([_API_KEY_RULE])
        result = pipe.apply("sk-abcdef1234567890 and sk-zzzz9999yyy0000a")
        assert isinstance(result, RedactionResult)
        assert result.text.count(_REDACTED_PREFIX) == 2
        assert result.counts == {"api_key": 2}
        assert result.redacted is True

    def test_pipeline_empty_rules_returns_text(self) -> None:
        pipe = RedactionPipeline([])
        result = pipe.apply("plain text")
        assert result.text == "plain text"
        assert result.redacted is False
        assert result.counts == {}

    def test_pipeline_redacted_false_when_no_match(self) -> None:
        pipe = RedactionPipeline([_API_KEY_RULE])
        result = pipe.apply("nothing to redact")
        assert result.redacted is False
        assert result.text == "nothing to redact"


class TestApplyRedactionFunction:
    def test_standalone_function_matches_pipeline(self) -> None:
        rules = [_API_KEY_RULE, _EMAIL_RULE]
        text = "sk-abcdef1234567890 <a@b.com>"
        via_func = apply_redaction(text, rules)
        via_pipe = RedactionPipeline(rules).apply(text)
        assert via_func == via_pipe.text

    def test_standalone_function_no_match(self) -> None:
        assert apply_redaction("hello world", [_API_KEY_RULE]) == "hello world"

    def test_original_secret_never_in_output(self) -> None:
        secret = "sk-supersecretvalue-1234567890"
        out = apply_redaction(f"key={secret}", [_API_KEY_RULE])
        assert secret not in out


def _extract_replacement(original_substring: str, output: str) -> str:
    """Find the ``<REDACTED:...>`` token that replaced *original_substring* in *output*.

    Picks the first redaction token (works because the test inputs have exactly one).
    """
    match = re.search(r"<REDACTED:[0-9a-f]{16}>", output)
    if not match:
        pytest.fail(f"no redaction token found in output: {output!r}")
    return match.group(0)

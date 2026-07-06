"""Redaction pass applied to memory content before persisting (MEMORY_CONTRACT rule 1)."""

from __future__ import annotations

from opencontext_memory.redaction import redact_memory_text


def test_fake_provider_token_is_redacted() -> None:
    fake = "sk-proj-abcdef1234567890abcdef1234567890"
    out = redact_memory_text(f"deploy with api_key={fake} today")
    assert fake not in out
    assert "[REDACTED" in out


def test_inline_env_assignment_is_redacted() -> None:
    # Not at line start and not a stand-alone key shape: only the inline
    # NAME=value pass catches it.
    out = redact_memory_text("Use AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLEKEY9 for deploys")
    assert "AKIAIOSFODNN7EXAMPLEKEY9" not in out
    assert "for deploys" in out


def test_plain_text_is_unchanged() -> None:
    text = "Root cause: missing select_related on the user queryset."
    assert redact_memory_text(text) == text


def test_empty_text_is_unchanged() -> None:
    assert redact_memory_text("") == ""


def test_already_redacted_value_is_not_double_redacted() -> None:
    text = "api_key=[REDACTED:openai_api_key] stays as is"
    assert redact_memory_text(text) == text

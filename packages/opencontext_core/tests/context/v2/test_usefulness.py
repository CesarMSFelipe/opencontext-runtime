"""Tests for context.v2.usefulness — CONV2 #11 relevance score."""

from __future__ import annotations

from opencontext_core.context.v2.usefulness import usefulness_score


def test_usefulness_positive_when_query_terms_overlap_content() -> None:
    score = usefulness_score({"content": "auth login returns 500"}, "login error")
    assert score > 0.0


def test_usefulness_zero_for_empty_query() -> None:
    assert usefulness_score({"content": "anything"}, "") == 0.0


def test_usefulness_zero_for_empty_content() -> None:
    assert usefulness_score({"content": ""}, "anything") == 0.0


def test_usefulness_zero_when_no_overlap() -> None:
    assert usefulness_score({"content": "cats and dogs"}, "auth login") == 0.0

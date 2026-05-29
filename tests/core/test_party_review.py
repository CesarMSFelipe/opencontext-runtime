"""Tests for party mode review — role prompts and report merging."""

from __future__ import annotations

from opencontext_cli.commands.review_cmd import (
    PARTY_ROLES,
    generate_role_prompt,
    merge_reports,
)

# ── generate_role_prompt ─────────────────────────────────────────────────────


def test_generate_role_prompt_includes_role_persona() -> None:
    """Generated prompt includes the role's persona instructions."""
    prompt = generate_role_prompt("architect", "some context")
    assert "Architect" in prompt or "architect" in prompt.lower()
    assert "some context" in prompt


def test_generate_role_prompt_all_builtin_roles() -> None:
    """All 4 built-in roles generate non-empty prompts."""
    for role in PARTY_ROLES:
        prompt = generate_role_prompt(role, "context here")
        assert len(prompt) > 50
        assert "context here" in prompt


def test_generate_role_prompt_unknown_role_falls_back() -> None:
    """Unknown roles fall back to architect persona without raising."""
    prompt = generate_role_prompt("nonexistent-role", "some code")
    assert "some code" in prompt
    assert len(prompt) > 20


def test_generate_role_prompt_asks_for_json_output() -> None:
    """Generated prompt requests structured JSON output."""
    prompt = generate_role_prompt("security", "def login(): pass")
    assert "JSON" in prompt or "json" in prompt.lower()


# ── merge_reports ────────────────────────────────────────────────────────────


def test_merge_empty_reports() -> None:
    """Merging zero reports produces a valid (empty) markdown report."""
    report = merge_reports([])
    assert "Party Mode Review Report" in report


def test_merge_reports_groups_by_severity() -> None:
    """Findings are grouped by severity in the merged report."""
    reports = [
        {
            "role": "architect",
            "findings": [
                {
                    "severity": "high",
                    "title": "Coupling issue",
                    "details": "Module A depends on B.",
                },
                {"severity": "low", "title": "Style nit", "details": "Minor issue."},
            ],
            "summary": "Architecture needs work.",
        },
        {
            "role": "security",
            "findings": [
                {
                    "severity": "high",
                    "title": "SQL injection risk",
                    "details": "Unsanitized input.",
                },
            ],
            "summary": "Critical security issues found.",
        },
    ]
    merged = merge_reports(reports)
    assert "High" in merged
    assert "Low" in merged
    assert "Coupling issue" in merged
    assert "SQL injection risk" in merged
    assert "Style nit" in merged


def test_merge_reports_includes_per_role_summaries() -> None:
    """Merged report includes each role's summary."""
    reports = [
        {"role": "architect", "findings": [], "summary": "Looks good overall."},
        {"role": "ux", "findings": [], "summary": "DX needs improvement."},
    ]
    merged = merge_reports(reports)
    assert "Looks good overall." in merged
    assert "DX needs improvement." in merged


def test_merge_reports_includes_reviewer_names() -> None:
    """Merged report lists reviewer names in the header."""
    reports = [
        {"role": "architect", "findings": [], "summary": "ok"},
        {"role": "performance", "findings": [], "summary": "ok"},
    ]
    merged = merge_reports(reports)
    assert "architect" in merged
    assert "performance" in merged

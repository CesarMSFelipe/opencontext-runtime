"""Tests for the dispatcher markdown + native phase prompt (REQ-OSS-004/005, REQ-GAS-005)."""

from __future__ import annotations

from opencontext_sdd.dispatcher import (
    RenderDispatcherMarkdown,
    RenderNativePhasePrompt,
)
from opencontext_sdd.status import Status

# ---------------------------------------------------------------------------
# REQ-OSS-004 — RenderDispatcherMarkdown
# ---------------------------------------------------------------------------


def test_REQ_OSS_004_dispatcher_markdown_includes_next_recommended() -> None:
    """Markdown block contains the change name and current ``nextRecommended``."""
    status = Status(
        changeName="demo",
        nextRecommended="spec",
        blockedReasons=["missing:specs/<cap>/spec.md"],
        artifactPaths={"proposal": "openspec/changes/demo/proposal.md"},
    )
    md = RenderDispatcherMarkdown(status)
    assert "Change: demo" in md
    assert "Next: spec" in md
    assert "openspec/changes/demo/specs/<cap>/spec.md" in md or "spec.md" in md


def test_REQ_OSS_004_dispatcher_markdown_blocked_list_section() -> None:
    """Blocked reasons appear under a ``Blocked:`` heading in the markdown."""
    status = Status(
        changeName="demo",
        nextRecommended="design",
        blockedReasons=["missing:design.md", "missing:tasks.md"],
    )
    md = RenderDispatcherMarkdown(status)
    assert "Blocked:" in md
    assert "missing:design.md" in md
    assert "missing:tasks.md" in md


def test_REQ_OSS_004_dispatcher_markdown_artifact_path_pointer() -> None:
    """Markdown points to the next artifact to write."""
    status = Status(
        changeName="demo",
        nextRecommended="design",
        artifactPaths={"proposal": "openspec/changes/demo/proposal.md"},
    )
    md = RenderDispatcherMarkdown(status)
    # Some pointer to the next artifact (design path or generic instruction).
    assert "design" in md.lower()


# ---------------------------------------------------------------------------
# REQ-OSS-005 — RenderNativePhasePrompt
# ---------------------------------------------------------------------------


def test_REQ_OSS_005_prompt_embeds_trace_id_and_phase() -> None:
    """Prompt contains ``trace_id=<id>`` AND ``phase=apply``."""
    prompt = RenderNativePhasePrompt("apply", change="demo", trace_id="tr-abc123")
    assert "trace_id=tr-abc123" in prompt
    assert "phase=apply" in prompt


def test_REQ_OSS_005_prompt_embeds_tdd_rule_when_strict() -> None:
    """Strict TDD mode embeds the test-first rule string."""
    prompt = RenderNativePhasePrompt("apply", change="demo", trace_id="tr-abc", tdd_mode="strict")
    assert "tdd-strict: write the closest failing test first" in prompt


def test_REQ_OSS_005_prompt_omits_tdd_rule_when_not_strict() -> None:
    """Non-strict mode does NOT embed the test-first rule string."""
    prompt = RenderNativePhasePrompt("apply", change="demo", trace_id="tr-abc", tdd_mode="ask")
    assert "tdd-strict: write the closest failing test first" not in prompt


def test_REQ_OSS_005_different_phases_distinct_prompts() -> None:
    """The renderer for ``verify`` and ``apply`` produce distinct output."""
    apply_prompt = RenderNativePhasePrompt("apply", trace_id="tr-1")
    verify_prompt = RenderNativePhasePrompt("verify", trace_id="tr-1")
    assert apply_prompt != verify_prompt
    assert "verify" not in apply_prompt.split("phase=apply")[1]
    assert "apply" not in verify_prompt.split("phase=verify")[1]


# ---------------------------------------------------------------------------
# REQ-GAS-005 — Deterministic per phase
# ---------------------------------------------------------------------------


def test_REQ_GAS_005_deterministic_per_phase() -> None:
    """Same inputs → same output, byte-for-byte (deterministic)."""
    a = RenderNativePhasePrompt("apply", change="demo", trace_id="tr-x", tdd_mode="strict")
    b = RenderNativePhasePrompt("apply", change="demo", trace_id="tr-x", tdd_mode="strict")
    assert a == b

    # Two phases with identical kwargs still differ (phase is part of the prompt).
    p_apply = RenderNativePhasePrompt("apply", change="demo", trace_id="tr-x")
    p_propose = RenderNativePhasePrompt("propose", change="demo", trace_id="tr-x")
    assert p_apply != p_propose


def test_REQ_GAS_005_prompt_contains_trace_id_and_tdd_rule_when_strict() -> None:
    """Combined assertion: trace_id + TDD rule coexist when strict."""
    prompt = RenderNativePhasePrompt("apply", change="demo", trace_id="tr-xyz", tdd_mode="strict")
    assert "trace_id=tr-xyz" in prompt
    assert "phase=apply" in prompt
    assert "tdd-strict: write the closest failing test first" in prompt

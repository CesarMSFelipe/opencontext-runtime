"""Structural / whole-token guardrail matching tests ().

The legacy evaluator used naive ``substring in text`` matching, which fires on
superstring words (e.g. "too broad" inside "too broadcast"). The upgraded
evaluator must match on whole, normalized tokens.
"""

from __future__ import annotations

from opencontext_core.agents.sdd_guardrails import evaluate_guardrails


class TestWholeTokenMatching:
    def test_does_not_false_positive_on_superstring_word(self) -> None:
        # "explore-too-broad" forbids the rationalization "too broad".
        # "too broadcast" merely *contains* "too broad" as a substring; the
        # whole-token matcher must NOT fire here.
        hits = evaluate_guardrails("explore", "the scope was too broadcast-heavy")
        assert all(h.name != "explore-too-broad" for h in hits)

    def test_does_not_false_positive_on_vagueness(self) -> None:
        # "tasks-too-vague" forbids "task is too vague"; "too vagueness" must
        # not trigger it via substring containment.
        hits = evaluate_guardrails("tasks", "this task is too vagueness aside")
        assert all(h.name != "tasks-too-vague" for h in hits)

    def test_whole_token_phrase_still_matches(self) -> None:
        # All tokens present as whole words -> guardrail fires.
        hits = evaluate_guardrails("explore", "this exploration is too broad in scope")
        assert any(h.name == "explore-too-broad" for h in hits)

    def test_case_insensitive_whole_token(self) -> None:
        hits = evaluate_guardrails("spec", "TOO SIMPLE FOR A SPEC")
        assert any(h.name == "too-simple-for-spec" for h in hits)

    def test_apply_block_whole_token(self) -> None:
        hits = evaluate_guardrails("apply", "I am implementing without writing tests right now")
        assert any(h.name == "apply-without-test" and h.severity == "block" for h in hits)

    def test_apply_no_false_positive_partial(self) -> None:
        # "tests" present but the "without writing" tokens are not -> no block.
        hits = evaluate_guardrails("apply", "implementing with thorough tests")
        assert all(h.name != "apply-without-test" for h in hits)

    def test_legacy_simple_phrase_still_matches(self) -> None:
        hits = evaluate_guardrails("spec", "This is too simple for a spec, honestly.")
        assert any(h.name == "too-simple-for-spec" for h in hits)

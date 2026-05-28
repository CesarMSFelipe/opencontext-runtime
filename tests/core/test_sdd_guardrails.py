"""Tests for SDD guardrails catalogue and evaluator."""

from __future__ import annotations

from opencontext_core.agents.sdd_guardrails import (
    CATALOGUE,
    GuardrailHit,
    evaluate_guardrails,
    get_catalogue,
    get_guardrails_for_phase,
)


class TestCatalogue:
    """Test guardrail catalogue."""

    def test_catalogue_non_empty(self) -> None:
        assert len(CATALOGUE) >= 8

    def test_each_entry_has_all_fields(self) -> None:
        for entry in CATALOGUE:
            assert entry.name
            assert entry.phases
            assert entry.rationalization
            assert entry.counter_argument
            assert entry.severity in ("warning", "block")

    def test_catalogue_includes_too_simple_for_spec(self) -> None:
        names = [e.name for e in CATALOGUE]
        assert "too-simple-for-spec" in names
        entry = next(e for e in CATALOGUE if e.name == "too-simple-for-spec")
        assert "spec" in entry.phases
        assert entry.severity == "warning"

    def test_get_guardrails_for_spec_phase(self) -> None:
        entries = get_guardrails_for_phase("spec")
        assert len(entries) >= 1
        assert all("spec" in e.phases for e in entries)

    def test_unknown_phase_returns_empty(self) -> None:
        entries = get_guardrails_for_phase("nonexistent")
        assert entries == []


class TestEvaluateGuardrails:
    """Test runtime guardrail evaluator."""

    def test_rationalization_detected_yields_warning(self) -> None:
        hits = evaluate_guardrails("spec", "This is too simple for a spec")
        assert len(hits) >= 1
        assert any(h.severity == "warning" for h in hits)

    def test_no_pattern_returns_empty(self) -> None:
        hits = evaluate_guardrails("spec", "This is a well-defined feature with clear requirements")
        assert hits == []

    def test_block_severity_returned(self) -> None:
        hits = evaluate_guardrails("apply", "implementing without writing tests")
        assert len(hits) >= 1
        assert any(h.severity == "block" for h in hits)

    def test_unknown_phase_no_crash(self) -> None:
        hits = evaluate_guardrails("unknown", "some content")
        assert hits == []

    def test_empty_context_no_crash(self) -> None:
        hits = evaluate_guardrails("spec", "")
        assert hits == []

    def test_case_insensitive_match(self) -> None:
        hits = evaluate_guardrails("spec", "TOO SIMPLE FOR A SPEC")
        assert len(hits) >= 1

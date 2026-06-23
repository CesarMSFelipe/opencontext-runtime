"""The skills subsystem is wired into the phase executor context.

``run_phase_executor`` must resolve builtin skills for the running phase and
inject their COMPACT rules into the ``context`` dict it hands to the delegate —
in addition to (never replacing) the prior artifact + explore pack.

These tests prove:
1. ``resolve_skills`` is actually invoked from ``run_phase_executor`` (it had
   zero callers before this wiring).
2. A matching skill's compact rules land in the executor's ``context`` under an
   ``## Applicable skills`` section, while the prior artifact + pack survive.
3. The injection is best-effort: a registry/resolver failure never breaks the
   executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import opencontext_core.harness.phases as phases_mod
from opencontext_core.harness.phases import run_phase_executor


@dataclass
class _FakeResult:
    status: str = "success"
    output: str = "ARTIFACT"
    error: str | None = None


@dataclass
class _CapturingDelegate:
    """A delegate whose ``delegate(phase, context)`` records the context dict."""

    captured: dict[str, Any] = field(default_factory=dict)

    def delegate(self, phase: str, context: dict[str, Any]) -> _FakeResult:
        self.captured["phase"] = phase
        self.captured["context"] = context
        return _FakeResult()


@dataclass
class _FakeState:
    delegate: Any
    task: str = "do the thing"
    run_id: str = "run-1"
    root: str = "/tmp/proj"
    prior_artifact: str = ""
    context_pack: str = ""


def _fresh_registry_cache() -> None:
    """Reset the module-level builtin-registry cache between scenarios."""
    phases_mod._BUILTIN_SKILL_REGISTRY = None
    phases_mod._BUILTIN_SKILL_REGISTRY_BUILT = False


def test_resolve_skills_is_invoked_by_executor(monkeypatch) -> None:
    """run_phase_executor calls resolve_skills (proving the dead seam is wired)."""
    _fresh_registry_cache()
    calls: list[dict[str, Any]] = []

    real_resolve = phases_mod.__dict__.get("resolve_skills")
    assert real_resolve is None  # imported lazily inside the helper, not at module scope

    import opencontext_core.skills.resolver as resolver_mod

    original = resolver_mod.resolve_skills

    def _spy(registry, *, file_patterns, task_type, max_matches):
        calls.append(
            {
                "task_type": task_type,
                "file_patterns": file_patterns,
                "max_matches": max_matches,
            }
        )
        return original(
            registry,
            file_patterns=file_patterns,
            task_type=task_type,
            max_matches=max_matches,
        )

    monkeypatch.setattr(resolver_mod, "resolve_skills", _spy)

    delegate = _CapturingDelegate()
    outcome = run_phase_executor(_FakeState(delegate=delegate), "design")

    assert outcome.executor == "real"
    assert calls, "resolve_skills was never called from run_phase_executor"
    # Called with the phase as the task type, empty file patterns, capped at <=2.
    assert calls[0]["task_type"] == "design"
    assert calls[0]["file_patterns"] == []
    assert calls[0]["max_matches"] <= 2


def test_matching_skill_rules_appear_in_executor_context() -> None:
    """A matching builtin skill's compact rules land in context['context']."""
    _fresh_registry_cache()
    delegate = _CapturingDelegate()

    run_phase_executor(_FakeState(delegate=delegate), "design")

    ctx = delegate.captured["context"]["context"]
    assert "## Applicable skills" in ctx
    # The design skill's compact rules are present (compact, not the full body).
    assert "oc-design-rules" in ctx
    assert "Reuse existing symbols before adding new ones" in ctx


def test_skills_added_in_addition_to_prior_artifact_and_pack() -> None:
    """Skill rules are appended; prior artifact + explore pack are preserved."""
    _fresh_registry_cache()
    delegate = _CapturingDelegate()
    state = _FakeState(
        delegate=delegate,
        prior_artifact="PRIOR_SPEC_BODY",
        context_pack="EXPLORE_PACK_BODY",
    )

    run_phase_executor(state, "design")

    ctx = delegate.captured["context"]["context"]
    assert "PRIOR_SPEC_BODY" in ctx
    assert "EXPLORE_PACK_BODY" in ctx
    assert "## Applicable skills" in ctx
    # Prior artifact still comes before the appended skills section.
    assert ctx.index("PRIOR_SPEC_BODY") < ctx.index("## Applicable skills")


def test_no_matching_skill_injects_nothing() -> None:
    """A phase with no matching builtin skill gets no Applicable-skills section."""
    _fresh_registry_cache()
    delegate = _CapturingDelegate()
    state = _FakeState(delegate=delegate, context_pack="PACK")

    # "explore" has no builtin *-rules skill -> nothing injected.
    run_phase_executor(state, "explore")

    ctx = delegate.captured["context"]["context"]
    assert "## Applicable skills" not in ctx
    assert ctx == "PACK"


def test_skill_injection_failure_never_breaks_executor(monkeypatch) -> None:
    """If skill resolution raises, the executor still runs with base context."""
    _fresh_registry_cache()

    def _boom(*_a, **_k):
        raise RuntimeError("registry exploded")

    # Force the helper's internal path to raise; it must be swallowed.
    monkeypatch.setattr(phases_mod, "_builtin_skill_registry", _boom)

    delegate = _CapturingDelegate()
    state = _FakeState(delegate=delegate, context_pack="PACK")
    outcome = run_phase_executor(state, "design")

    assert outcome.executor == "real"
    ctx = delegate.captured["context"]["context"]
    assert ctx == "PACK"
    assert "## Applicable skills" not in ctx
